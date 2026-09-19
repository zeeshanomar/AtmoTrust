import csv
import asyncio
import json
import os
import time
from pathlib import Path
import httpx
from .schema import Observation, SourceStatus, UNITS, now

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("ATMOTRUST_DATA_DIR", str(ROOT / "data/prepared/demo_v1")))
if not DATA_DIR.is_absolute():
    DATA_DIR = ROOT / DATA_DIR


class PreparedSource:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = Path(data_dir)
        self.stations = json.loads((self.data_dir / "stations.json").read_text(encoding="utf-8"))
        self.manifest = json.loads((self.data_dir / "manifest.json").read_text(encoding="utf-8"))
        self.policy = json.loads((self.data_dir / "policy.json").read_text(encoding="utf-8"))
        self.frames = {}
        with (self.data_dir / "observations.csv").open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                self.frames.setdefault(int(row["sequence"]), []).append(row)
        self.total_frames = len(self.frames)
        assert all(len(frame) == len(self.stations) * len(UNITS) for frame in self.frames.values())

    def read_frame(self, sequence: int, run_id="reference", generation=1):
        if sequence not in self.frames:
            raise IndexError(sequence)
        return [Observation(sample_id=f"{run_id}:{generation}:{sequence}:{row['station_id']}:{row['variable']}", run_id=run_id, generation=generation, sequence=sequence, station_id=row["station_id"], timestamp=row["timestamp"], variable=row["variable"], value=float(row["value"]) if row["value"] else None, unit=UNITS[row["variable"]], source_mode="replay", source_name=self.manifest["source_name"], source_timestamp=row["timestamp"], received_at=now(), raw_value=float(row["value"]) if row["value"] else None) for row in self.frames[sequence]]

    def status(self):
        return SourceStatus(source_mode="replay", source_name=self.manifest["source_name"], provenance_type=self.manifest["provenance_type"], status="available", source_timestamp=self.manifest["end"], detail="Prepared offline replay; logical locations are not physical AWS sensors.")


class LiveAdapter:
    def __init__(self, stations):
        self.stations = stations
        self.last_success = None
        self.cache = []
        self.cache_at = 0.0

    async def fetch_latest(self, run_id, generation, sequence):
        if self.cache and time.monotonic() - self.cache_at < 60:
            copied = [item.model_copy(update={"sample_id": f"{run_id}:{generation}:{sequence}:{item.station_id}:{item.variable}", "run_id": run_id, "generation": generation, "sequence": sequence}) for item in self.cache]
            return copied, SourceStatus(source_mode="live", source_name="open_meteo_current_gridded", provenance_type="current_gridded_location", status="available", source_timestamp=copied[0].source_timestamp, fetched_at=self.last_success, detail="Cached genuine provider readings (up to 60 seconds); not a new provider fetch.")
        observations = []
        fetched_at = now()
        try:
            async with httpx.AsyncClient(timeout=6) as client:
                async def one(station):
                    response = await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": station["latitude"], "longitude": station["longitude"], "current": "temperature_2m,relative_humidity_2m,pressure_msl", "timezone": "UTC"})
                    response.raise_for_status()
                    current = response.json()["current"]
                    stamp = current["time"] + ("Z" if not current["time"].endswith("Z") else "")
                    local = []
                    for variable, key in (("temperature_c", "temperature_2m"), ("pressure_hpa", "pressure_msl"), ("humidity_pct", "relative_humidity_2m")):
                        value = current[key]
                        if not isinstance(value, (int, float)):
                            raise ValueError(f"Invalid {key}")
                        local.append(Observation(sample_id=f"{run_id}:{generation}:{sequence}:{station['station_id']}:{variable}", run_id=run_id, generation=generation, sequence=sequence, station_id=station["station_id"], timestamp=stamp, variable=variable, value=float(value), raw_value=float(value), unit=UNITS[variable], source_mode="live", source_name="open_meteo_current_gridded", source_timestamp=stamp, received_at=fetched_at))
                    return local
                batches = await asyncio.wait_for(asyncio.gather(*(one(station) for station in self.stations)), timeout=7)
                observations = [item for batch in batches for item in batch]
            self.last_success = fetched_at
            self.cache = observations
            self.cache_at = time.monotonic()
            return observations, SourceStatus(source_mode="live", source_name="open_meteo_current_gridded", provenance_type="current_gridded_location", status="available", source_timestamp=observations[0].source_timestamp, fetched_at=fetched_at, detail="Current provider readings for logical coordinates; not physical AWS telemetry.")
        except (httpx.HTTPError, asyncio.TimeoutError, KeyError, TypeError, ValueError) as exc:
            return [], SourceStatus(source_mode="live", source_name="open_meteo_current_gridded", provenance_type="current_gridded_location", status="unavailable", fetched_at=fetched_at, detail=f"Provider unavailable: {type(exc).__name__}; last successful fetch: {self.last_success or 'none'}")
