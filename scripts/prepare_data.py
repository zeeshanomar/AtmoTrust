"""Prepare an offline, explicitly provenance-labelled five-location replay package."""
import csv
import hashlib
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/prepared/demo_v1"
STATIONS = [
    {"station_id": "CHD-01", "name": "Chandigarh", "latitude": 30.7333, "longitude": 76.7794, "criticality": 0.9},
    {"station_id": "MOH-01", "name": "Mohali", "latitude": 30.7046, "longitude": 76.7179, "criticality": 0.7},
    {"station_id": "PKL-01", "name": "Panchkula", "latitude": 30.6942, "longitude": 76.8606, "criticality": 0.7},
    {"station_id": "AMB-01", "name": "Ambala", "latitude": 30.3782, "longitude": 76.7767, "criticality": 0.8},
    {"station_id": "PTA-01", "name": "Patiala", "latitude": 30.3398, "longitude": 76.3869, "criticality": 0.7},
]
VARIABLES = {"temperature_c": ("temperature_2m", "°C"), "pressure_hpa": ("pressure_msl", "hPa"), "humidity_pct": ("relative_humidity_2m", "%")}
POLICY = {"weights": {"physical": 0.15, "temporal": 0.20, "expected": 0.20, "spatial": 0.20, "multivariate": 0.15, "isolation_forest": 0.10}, "minimum_evidence_coverage": 0.60, "history_window": 24}


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def fetch(station):
    cache_dir = ROOT / "data/raw/open_meteo"
    cache_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    hourly = {"time": [], "temperature_2m": [], "relative_humidity_2m": [], "pressure_msl": []}
    for day in (1, 8, 15, 22):
        start, end = f"2026-08-{day:02d}", f"2026-08-{day + 6:02d}"
        query = urllib.parse.urlencode({"latitude": station["latitude"], "longitude": station["longitude"], "start_date": start, "end_date": end, "hourly": "temperature_2m,relative_humidity_2m,pressure_msl", "timezone": "UTC"})
        url = "https://archive-api.open-meteo.com/v1/archive?" + query
        cache = cache_dir / f"{station['station_id']}_{start}_{end}.json"
        if cache.exists():
            payload = json.loads(cache.read_text(encoding="utf-8"))
        else:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AtmoTrust-demo-data/1.0"}), timeout=25) as response:
                payload = json.load(response)
            cache.write_text(json.dumps(payload), encoding="utf-8")
        urls.append(url)
        expected_units = {"temperature_2m": "°C", "relative_humidity_2m": "%", "pressure_msl": "hPa"}
        if any(payload.get("hourly_units", {}).get(key) != unit for key, unit in expected_units.items()):
            raise ValueError("Unexpected Open-Meteo units")
        for key in hourly:
            hourly[key].extend(payload["hourly"][key])
    n = len(hourly["time"])
    if n < 600 or any(len(hourly[source]) != n for source, _ in VARIABLES.values()):
        raise ValueError("Historical response lacks sufficient aligned hourly data")
    if hourly["time"] != sorted(set(hourly["time"])):
        raise ValueError("Historical time axis is not strictly increasing")
    if any(value is not None and not (-35 <= value <= 60) for value in hourly["temperature_2m"]):
        raise ValueError("Temperature outside conservative bounds")
    if any(value is not None and not (870 <= value <= 1085) for value in hourly["pressure_msl"]):
        raise ValueError("Pressure outside conservative bounds")
    if any(value is not None and not (0 <= value <= 100) for value in hourly["relative_humidity_2m"]):
        raise ValueError("Humidity outside physical bounds")
    return urls, {"hourly": hourly}


def synthetic(station, station_index):
    start = datetime(2025, 8, 1, tzinfo=timezone.utc)
    hourly = {"time": [], "temperature_2m": [], "relative_humidity_2m": [], "pressure_msl": []}
    for i in range(720):
        h = i % 24
        slow = math.sin(i / 41)
        hourly["time"].append((start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M"))
        hourly["temperature_2m"].append(round(29 + 5 * math.sin((h - 8) * math.pi / 12) + 1.1 * slow + station_index * 0.18, 2))
        hourly["relative_humidity_2m"].append(round(66 - 13 * math.sin((h - 8) * math.pi / 12) - 3 * slow + station_index * 0.3, 2))
        hourly["pressure_msl"].append(round(1005 + 2 * math.sin(i / 35) + station_index * 0.12, 2))
    return hourly


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records, urls, source = [], [], "open_meteo_archive_gridded"
    try:
        fetched = [fetch(station) for station in STATIONS]
        urls = [url for station_urls, _ in fetched for url in station_urls]
        hourly_by_station = [payload["hourly"] for _, payload in fetched]
        times = hourly_by_station[0]["time"]
        if any(hourly["time"] != times for hourly in hourly_by_station):
            raise ValueError("Stations do not share one hourly timeline")
    except (OSError, KeyError, ValueError, TimeoutError) as exc:
        if "--allow-synthetic" not in sys.argv:
            raise RuntimeError("Archive unavailable; rerun with --allow-synthetic for the documented offline fallback") from exc
        source = "synthetic_demo"
        hourly_by_station = [synthetic(station, i) for i, station in enumerate(STATIONS)]
        times = hourly_by_station[0]["time"]
        print(f"Archive unavailable, using labelled deterministic fallback: {exc}")
    for station, hourly in zip(STATIONS, hourly_by_station):
        for i, stamp in enumerate(times):
            timestamp = stamp + ":00Z"
            for variable, (source_key, _) in VARIABLES.items():
                value = hourly[source_key][i]
                records.append((i, timestamp, station["station_id"], variable, "" if value is None else value))
    with (OUT / "observations.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["sequence", "timestamp", "station_id", "variable", "value"])
        writer.writerows(records)
    table = pd.read_csv(OUT / "observations.csv")
    if len(table) != len(records) or table.duplicated(["station_id", "variable", "timestamp"]).any():
        raise ValueError("Prepared data failed row count or uniqueness validation")
    if table.groupby(["station_id", "variable"])["sequence"].nunique().min() != len(times):
        raise ValueError("Prepared data lacks complete station-variable overlap")
    write_json("stations.json", STATIONS)
    write_json("peer_links.json", {station["station_id"]: [other["station_id"] for other in STATIONS if other != station] for station in STATIONS})
    write_json("policy.json", POLICY)
    hashes = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in ["observations.csv", "stations.json", "peer_links.json", "policy.json"]}
    manifest = {"dataset_id": "demo_v1", "source_name": source, "provenance_type": "gridded_reanalysis" if urls else "synthetic_demonstration", "source_urls": urls, "retrieved_at": datetime.now(timezone.utc).isoformat(), "start": times[0] + ":00Z", "end": times[-1] + ":00Z", "cadence": "1 hour", "pressure_reference": "mean_sea_level", "units": {v: unit for v, (_, unit) in VARIABLES.items()}, "rows": len(records), "frames": len(times), "missing": sum(row[-1] == "" for row in records), "hashes": hashes}
    write_json("manifest.json", manifest)
    (OUT / "data_report.md").write_text(f"# demo_v1 data\n\n{len(STATIONS)} logical locations, {len(times)} hourly frames, {len(records)} variable rows. Source: `{source}`. Pressure: mean sea level. Missing rows: {manifest['missing']}. These are location/grid values, never physical AWS readings.\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("source_name", "frames", "rows", "missing")}))


if __name__ == "__main__":
    main()
