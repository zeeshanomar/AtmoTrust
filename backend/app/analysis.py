"""Causal evidence fusion. Inputs here are model-safe projections only."""
import math
import hashlib
import json
import statistics
from pathlib import Path
import joblib
from .schema import Assessment, Evidence
from .health import RECOMMEND

SCALE = {"temperature_c": 1.8, "pressure_hpa": 0.7, "humidity_pct": 5.0}
BOUNDS = {"temperature_c": (-35, 60), "pressure_hpa": (870, 1085), "humidity_pct": (0, 100)}
REFERENCES = {"temperature_c": 25, "pressure_hpa": 1005, "humidity_pct": 60}
CLASSIFIER_FEATURES = ["current_scaled", "previous_scaled", "step_scaled", "rolling_mean_scaled", "rolling_std_scaled", "rolling_slope_scaled", "expected_residual_scaled", "peer_level_residual_scaled", "peer_movement_scaled", "repeat_run", "missing", "cross_variable_gap", "residual_persistence_scaled", "isolation_margin", "temperature", "pressure", "humidity"]


def clip(value, low=-1, high=1):
    return max(low, min(high, value))


def median(values):
    return statistics.median(values) if values else None


def score_band(score):
    if score <= 28:
        return "low", "likely_fault"
    if score <= 64:
        return "uncertain", "needs_review"
    if score <= 84:
        return "high", "likely_genuine"
    return "very_high", "likely_genuine"


class TrustEngine:
    def __init__(self, policy, artifact_path=None):
        self.policy = policy
        self.model = None
        self.classifier = None
        if artifact_path:
            try:
                artifact_path = Path(artifact_path)
                classifier_path = Path(artifact_path).with_name("fault_classifier.joblib")
                manifest_path = artifact_path.with_name("manifest.json")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                hashes = manifest["artifact_hashes"]
                if manifest["feature_order"] == CLASSIFIER_FEATURES and all(hashlib.sha256(path.read_bytes()).hexdigest() == hashes[path.name] for path in (artifact_path, classifier_path)):
                    self.model = joblib.load(artifact_path)
                    package = joblib.load(classifier_path)
                    if package["features"] == CLASSIFIER_FEATURES and self.model is not None:
                        self.classifier = package["model"]
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                self.model = None
                self.classifier = None

    def features(self, item, frame, history, stations):
        key = (item["station_id"], item["variable"])
        values = [row["value"] for row in history.get(key, []) if row["value"] is not None]
        value = item["value"]
        if value is None:
            return {"value": None, "values": values}
        last = values[-1] if values else None
        step = value - last if last is not None else None
        peers = []
        peer_steps = []
        peer_runs = []
        for station in stations:
            peer_id = station["station_id"]
            if peer_id == item["station_id"]:
                continue
            peer = frame.get((peer_id, item["variable"]))
            peer_history = [row["value"] for row in history.get((peer_id, item["variable"]), []) if row["value"] is not None]
            if peer and peer["value"] is not None:
                peers.append(peer["value"])
                if peer_history:
                    peer_steps.append(peer["value"] - peer_history[-1])
                if peer_history and len(peer_history) >= min(4, max(1, len(values))):
                    peer_runs.append(abs(peer["value"] - peer_history[-min(4, max(1, len(values)))]))
        peer_step = median(peer_steps)
        peer_value = median(peers)
        seasonal = values[-24] if len(values) >= 24 else None
        peer_seasonal_moves = []
        peer_seasonal_values = []
        if seasonal is not None:
            for station in stations:
                peer_id = station["station_id"]
                if peer_id == item["station_id"]:
                    continue
                peer = frame.get((peer_id, item["variable"]))
                pv = [row["value"] for row in history.get((peer_id, item["variable"]), []) if row["value"] is not None]
                if peer and peer["value"] is not None and len(pv) >= 24:
                    peer_seasonal_moves.append(peer["value"] - pv[-24])
                    peer_seasonal_values.append(pv[-24])
        expected = seasonal + median(peer_seasonal_moves) if seasonal is not None and len(peer_seasonal_moves) >= 2 else (last + peer_step if last is not None and peer_step is not None else last if last is not None else peer_value if len(peers) >= 2 else None)
        residual = value - expected if expected is not None else None
        spatial_residual = step - peer_step if step is not None and peer_step is not None else None
        spatial_level_residual = value - peer_value - (seasonal - median(peer_seasonal_values)) if seasonal is not None and peer_value is not None and len(peer_seasonal_values) >= 2 else value - peer_value if not values and len(peers) >= 2 else None
        repeated = 1
        for old in reversed(values):
            if old == value:
                repeated += 1
            else:
                break
        residual_series = []
        for old in list(history.get(key, []))[-6:]:
            if old.get("residual") is not None:
                residual_series.append(old["residual"])
        recent_changes = [values[i] - values[i - 1] for i in range(max(1, len(values) - 5), len(values))]
        return {"value": value, "values": values, "last": last, "step": step, "peer_step": peer_step, "peer_value": peer_value, "peer_count": len(peers), "peer_run_change": median(peer_runs), "expected": expected, "residual": residual, "spatial_residual": spatial_residual, "spatial_level_residual": spatial_level_residual, "repeated": repeated, "residual_series": residual_series, "recent_changes": recent_changes}

    @staticmethod
    def model_features(feature, variable):
        scale = SCALE[variable]
        return [abs(feature.get("step") or 0) / scale, abs(feature.get("residual") or 0) / scale, max(abs(feature.get("spatial_residual") or 0), abs(feature.get("spatial_level_residual") or 0)) / scale, min(feature.get("repeated", 1), 12) / 3]

    @staticmethod
    def classifier_features(feature, variable, station_features=None, isolation_margin=0):
        scale = SCALE[variable]
        values = feature.get("values", [])
        recent = values[-6:]
        slope = (recent[-1] - recent[0]) / max(1, len(recent) - 1) if len(recent) > 1 else 0
        residuals = feature.get("residual_series", [])
        spatial = feature.get("spatial_residual")
        others = []
        for other, peer in (station_features or {}).items():
            if other != variable and peer.get("spatial_residual") is not None:
                others.append(peer["spatial_residual"] / SCALE[other])
        cross = abs(spatial / scale - statistics.mean(others)) if spatial is not None and others else 0
        onehot = [int(variable == name) for name in ("temperature_c", "pressure_hpa", "humidity_pct")]
        def centered(value):
            return ((value if value is not None else REFERENCES[variable]) - REFERENCES[variable]) / scale
        return [centered(feature.get("value")), centered(feature.get("last")), (feature.get("step") or 0) / scale,
                centered(statistics.mean(recent) if recent else None), statistics.pstdev(recent) / scale if len(recent) > 1 else 0,
                slope / scale, (feature.get("residual") or 0) / scale,
                (feature.get("spatial_level_residual") or 0) / scale,
                (feature.get("spatial_residual") or 0) / scale,
                min(feature.get("repeated", 1), 12), int(feature.get("value") is None), cross,
                statistics.mean(residuals) / scale if residuals else 0, isolation_margin, *onehot]

    def analyze_frame(self, model_observations, history, stations, policy=None):
        policy = policy or self.policy
        frame = {(item["station_id"], item["variable"]): item for item in model_observations}
        features = {key: self.features(item, frame, history, stations) for key, item in frame.items()}
        margins = {}
        if self.model is not None:
            model_keys = [key for key, item in frame.items() if item["value"] is not None and len(features[key].get("values", [])) >= 24]
            if model_keys:
                values = self.model.decision_function([self.model_features(features[key], frame[key]["variable"]) for key in model_keys])
                margins = dict(zip(model_keys, map(float, values)))
        predictions = {}
        if self.classifier is not None:
            keys = [key for key in frame if len(features[key].get("values", [])) >= 24]
            if keys:
                vectors = [self.classifier_features(features[key], frame[key]["variable"], {v: features.get((key[0], v), {}) for v in SCALE}, margins.get(key, 0)) for key in keys]
                probabilities = self.classifier.predict_proba(vectors)
                predictions = {key: dict(zip(self.classifier.classes_, map(float, probability))) for key, probability in zip(keys, probabilities)}
        results = []
        for key, item in frame.items():
            variable, value = item["variable"], item["value"]
            f = features[key]
            base = dict(sample_id=item["sample_id"], station_id=item["station_id"], variable=variable, timestamp=item["timestamp"])
            if len(f.get("values", [])) < 24:
                results.append(Assessment(**base, assessment_status="insufficient_context", observed_value=value, explanation="Waiting for sufficient historical observations.", evidence=[Evidence(kind="context", label="Waiting for context", detail="At least 24 earlier observations are required.", support=0)]))
                continue
            if self.classifier is None or self.model is None:
                results.append(Assessment(**base, assessment_status="model_unavailable", observed_value=value, explanation="Analysis unavailable: saved model could not load."))
                continue
            if value is None:
                results.append(Assessment(**base, assessment_status="missing", fault_type="missing", severity="high", observed_value=None, confidence=round(predictions.get(key, {}).get("missing", 0), 2), explanation="An expected reading did not arrive; check power, telemetry, and communications.", resolution=RECOMMEND["missing"], evidence=[Evidence(kind="physical", label="Missing observation", detail="No usable value arrived for this expected slot.", support=-1)]))
                continue
            if not isinstance(value, (float, int)) or not math.isfinite(value) or not BOUNDS[variable][0] <= value <= BOUNDS[variable][1]:
                results.append(Assessment(**base, assessment_status="invalid", fault_type="bias", severity="critical", observed_value=value, explanation="Reading lies outside the physical validity range.", resolution=RECOMMEND["bias"], evidence=[Evidence(kind="physical", label="Outside safe range", detail=f"Observed {value} lies outside {BOUNDS[variable]} {variable} bounds.", support=-1)]))
                continue
            scale = SCALE[variable]
            evidence = []
            def add(kind, label, detail, support):
                evidence.append(Evidence(kind=kind, label=label, detail=detail, support=round(clip(support), 3)))
            step = f["step"]
            freeze_clue = f["repeated"] >= 4 and (f["peer_run_change"] or 0) > 0.5 * scale
            if step is None:
                add("physical", "Physical range", f"Observed {value:.2f} within safe {BOUNDS[variable]} {variable} bounds; no prior sample yet.", 0.6)
            else:
                direct = -1 if abs(step) > 5 * scale or freeze_clue else 0.85
                add("physical", "Direct checks", f"One-step change {step:+.2f} {variable}; repeated value run {f['repeated']}.", direct)
            if f["residual"] is not None:
                z = abs(f["residual"]) / scale
                support = clip(0.9 - 0.5 * z)
                add("expected", "Expected-value residual", f"Observed {value:.2f}, causal expected {f['expected']:.2f}; residual {f['residual']:+.2f} ({z:.1f} scale units).", support)
                past_residuals = f["residual_series"]
                slope = f["residual"] - past_residuals[0] if past_residuals else 0
                temporal = clip(0.85 - 0.45 * z - (1.5 if freeze_clue else 0))
                add("temporal", "Recent sensor history", f"Residual {f['residual']:+.2f}; {len(past_residuals)} prior residuals; run length {f['repeated']}.", temporal)
            if (f["spatial_residual"] is not None or f["spatial_level_residual"] is not None) and f["peer_count"] >= 2:
                difference = max(abs(f["spatial_residual"] or 0), abs(f["spatial_level_residual"] or 0), (f["peer_run_change"] or 0) if freeze_clue else 0) / scale
                spatial_support = -1 if freeze_clue else clip(0.95 - 0.65 * difference)
                detail = f"Target changed {step:+.2f}; median of {f['peer_count']} peers changed {f['peer_step']:+.2f}; level difference from prior peer relationship {(f['spatial_level_residual'] or 0):+.2f}; peer four-step movement {(f['peer_run_change'] or 0):.2f}." if step is not None and f["peer_step"] is not None else f"Current value differs from median of {f['peer_count']} peers by {(f['spatial_level_residual'] or 0):+.2f}; no prior trend yet."
                add("spatial", "Nearby peer agreement" if difference < 1 and not freeze_clue else "Nearby peers disagree", detail, spatial_support)
            others = [other for other in ("temperature_c", "pressure_hpa", "humidity_pct") if other != variable]
            other_differences = [(features[(item["station_id"], other)]["spatial_residual"] if features[(item["station_id"], other)]["spatial_residual"] is not None else features[(item["station_id"], other)]["spatial_level_residual"]) / SCALE[other] for other in others if features.get((item["station_id"], other), {}).get("spatial_residual") is not None or features.get((item["station_id"], other), {}).get("spatial_level_residual") is not None]
            spatial_delta = f["spatial_residual"] if f["spatial_residual"] is not None else f["spatial_level_residual"]
            if spatial_delta is not None and len(other_differences) == 2:
                relation_gap = abs(spatial_delta / scale - statistics.mean(other_differences))
                add("multivariate", "T/P/RH peer-normalized movement", f"Target channel differs from the other two peer-normalized channel changes by {relation_gap:.2f} scale units.", clip(0.8 - 0.45 * relation_gap))
            if key in margins:
                margin = margins[key]
                add("isolation_forest", "Learned normal pattern", f"Isolation Forest margin {margin:+.3f} relative to clean training frames.", clip(margin * 8))
            weights = policy["weights"]
            coverage = sum(weights[e.kind] for e in evidence)
            context = any(e.kind in ("temporal", "expected", "spatial", "multivariate") for e in evidence)
            if coverage < policy["minimum_evidence_coverage"] or not context:
                results.append(Assessment(**base, assessment_status="insufficient_context", evidence=[Evidence(kind="context", label="Waiting for context", detail=f"Evidence coverage {coverage:.2f}; need {policy['minimum_evidence_coverage']:.2f} and historical or peer context.", support=0)]))
                continue
            signed = sum(weights[e.kind] * e.support for e in evidence) / coverage
            evidence_score = max(0, min(100, 50 + 50 * signed))
            probabilities = predictions.get(key, {})
            clean_probability = probabilities.get("clean", 0)
            score = round(0.55 * evidence_score + 0.45 * clean_probability * 100)
            band, decision = score_band(score)
            agreement = 1 - statistics.pstdev([e.support for e in evidence]) / 2 if len(evidence) > 1 else 0.5
            predicted = max(probabilities, key=probabilities.get) if probabilities else "clean"
            fault = predicted if decision != "likely_genuine" and predicted != "clean" else "unknown"
            if decision != "likely_genuine" and spatial_delta is not None and step is not None and abs(spatial_delta) > 2.5 * scale and abs(step) > 2.5 * scale and (not f["residual_series"] or abs(f["residual_series"][-1]) < 1.5 * scale):
                fault = "spike"
            confidence = round(0.7 * probabilities.get(fault if fault != "unknown" else predicted, 0) + 0.3 * clip(agreement, 0, 1), 2)
            magnitude = abs(f["residual"] or 0) / scale
            severity = "none" if decision == "likely_genuine" else ("critical" if magnitude > 7 else "high" if magnitude > 4 or score <= 34 else "medium" if magnitude > 2 else "low")
            strongest = sorted(evidence, key=lambda e: abs(e.support), reverse=True)[:4]
            explanation = {"spike": f"Sudden change {step:+.2f} while nearby peers moved {(f['peer_step'] or 0):+.2f}.", "freeze": f"Value repeated {f['repeated']} times while nearby peers changed.", "drift": f"Residual {f['residual']:+.2f} has grown across recent samples.", "bias": f"Observed value is persistently offset by {f['residual']:+.2f} from the expected pattern.", "noise": f"Short-window changes vary unusually; latest residual {f['residual']:+.2f}.", "unknown": f"Observed minus expected is {f['residual']:+.2f}; review the measured evidence."}.get(fault, "Measured pattern requires review.")
            results.append(Assessment(**base, assessment_status="complete", trust_score=score, trust_band=band, decision=decision, confidence=confidence, severity=severity, fault_type=fault, expected_value=round(f["expected"], 3) if f["expected"] is not None else None, peer_value=round(f["peer_value"], 3) if f["peer_value"] is not None else None, observed_value=value, explanation=explanation, resolution=RECOMMEND.get(fault, RECOMMEND["unknown"]), evidence=strongest))
        return results, features
