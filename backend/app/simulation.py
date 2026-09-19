import math
import hashlib
from .schema import Observation, Injection


class ScenarioInjector:
    def __init__(self, seed=26073):
        self.seed = seed

    def apply(self, observations: list[Observation], active_injections: list[Injection], regional_event: dict | None, sequence: int, previous: dict | None = None):
        previous = previous or {}
        output = [item.model_copy(deep=True) for item in observations]
        if regional_event and regional_event["start_sequence"] <= sequence < regional_event["end_sequence"]:
            elapsed = sequence - regional_event["start_sequence"] + 1
            duration = regional_event["duration_samples"]
            ramp = min(4, max(1, duration / 2))
            common_profile = min(1, elapsed / ramp, (duration - elapsed + 1) / ramp)
            changes = {"temperature_c": -4.0, "pressure_hpa": -2.5, "humidity_pct": 11.0}
            for item in output:
                if item.value is not None:
                    station_hash = hashlib.sha256(f"{self.seed}:{item.station_id}".encode()).digest()
                    station_scale = 0.85 + 0.30 * station_hash[0] / 255
                    delta = changes[item.variable] * common_profile * station_scale
                    if item.variable == "humidity_pct":
                        delta = min(delta, max(0, 98 - item.value))
                    item.value = round(item.value + delta, 3)
                    item.is_test_overlay = True
        for injection in active_injections:
            if injection.status not in ("scheduled", "active"):
                continue
            if not injection.start_sequence <= sequence < injection.end_sequence:
                continue
            for item in output:
                if item.station_id != injection.station_id or item.variable != injection.variable:
                    continue
                elapsed = sequence - injection.start_sequence
                magnitude = injection.magnitude
                if injection.fault_type == "missing":
                    item.value = None
                elif injection.fault_type == "freeze":
                    item.value = previous.get((item.station_id, item.variable), item.value)
                elif item.value is not None:
                    if injection.fault_type == "spike":
                        item.value += magnitude
                    elif injection.fault_type == "bias":
                        item.value += magnitude
                    elif injection.fault_type == "drift":
                        item.value += magnitude * (elapsed + 1) / injection.duration_samples
                    elif injection.fault_type == "noise":
                        phase = (self.seed + sum(ord(c) for c in f"{injection.station_id}:{injection.variable}:{injection.start_sequence}")) % 17
                        item.value += magnitude * math.sin((elapsed + 1) * 2.399 + phase)
                if item.value is not None:
                    item.value = round(item.value, 3)
                item.is_test_overlay = True
        return output
