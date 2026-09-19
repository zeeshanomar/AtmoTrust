"""Offline chronological model training. Labels are simulated after splitting."""
import hashlib
import json
import platform
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import ExtraTreesClassifier, IsolationForest, RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support, recall_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.analysis import CLASSIFIER_FEATURES, TrustEngine
from app.data import PreparedSource
from app.schema import Injection, now
from app.simulation import ScenarioInjector

LABELS = ["clean", "spike", "freeze", "drift", "bias", "noise", "missing"]


def split_bounds(total):
    return {"train": (0, int(total * .70)), "validation": (int(total * .70), int(total * .85)), "test": (int(total * .85), total)}


def frame_vectors(engine, observations, history, stations):
    safe = [item.model_input() for item in observations]
    frame = {(item["station_id"], item["variable"]): item for item in safe}
    features = {key: engine.features(item, frame, history, stations) for key, item in frame.items()}
    valid = [key for key, item in frame.items() if item["value"] is not None and len(features[key].get("values", [])) >= 24]
    margins = dict(zip(valid, map(float, engine.model.decision_function([engine.model_features(features[key], key[1]) for key in valid])))) if valid else {}
    vectors = {key: engine.classifier_features(feature, key[1], {var: features.get((key[0], var), {}) for var in ("temperature_c", "pressure_hpa", "humidity_pct")}, margins.get(key, 0)) for key, feature in features.items() if len(feature.get("values", [])) >= 24}
    for key, item in frame.items():
        history[key].append({**item, "residual": features[key].get("residual")})
    return vectors


def build_dataset(source, engine, begin, end):
    history = defaultdict(lambda: deque(maxlen=60))
    X, y = [], []
    for sequence in range(begin, end):
        for vector in frame_vectors(engine, source.read_frame(sequence), history, source.stations).values():
            X.append(vector); y.append("clean")
    injector = ScenarioInjector()
    stations = [station["station_id"] for station in source.stations]
    variables = ("temperature_c", "pressure_hpa", "humidity_pct")
    for ordinal, start in enumerate(range(begin + 25, end - 6, 11)):
        for fault in LABELS[1:]:
            for variable in variables:
                station_id = stations[(ordinal + LABELS.index(fault)) % len(stations)]
                magnitude = {"temperature_c": 10, "pressure_hpa": 7, "humidity_pct": 22}[variable]
                duration = 1 if fault == "spike" else 5
                injection = Injection(station_id=station_id, variable=variable, fault_type=fault, magnitude=magnitude, duration_samples=duration, injection_id=f"train-{start}-{fault}-{variable}", start_sequence=start, end_sequence=start + duration)
                episode = defaultdict(lambda: deque(maxlen=60))
                for sequence in range(start - 24, start + 5):
                    observations = source.read_frame(sequence)
                    if sequence >= start:
                        previous = {key: values[-1]["value"] for key, values in episode.items() if values}
                        observations = injector.apply(observations, [injection], None, sequence, previous)
                    vectors = frame_vectors(engine, observations, episode, source.stations)
                    if start <= sequence < start + duration and (station_id, variable) in vectors:
                        X.append(vectors[(station_id, variable)]); y.append(fault)
    return np.asarray(X, dtype=float), np.asarray(y)


def evaluate(model, X, y):
    started = time.perf_counter()
    predicted = model.predict(X)
    latency = (time.perf_counter() - started) * 1000 / max(1, len(X))
    truth, found = y != "clean", predicted != "clean"
    p, r, f, _ = precision_recall_fscore_support(y, predicted, labels=LABELS, zero_division=0)
    return {"macro_f1": round(float(f1_score(y, predicted, labels=LABELS, average="macro", zero_division=0)), 4), "strict_fault_recall": round(float(recall_score(truth, found, zero_division=0)), 4), "false_alarm_rate": round(float(np.mean(found[~truth])) if np.any(~truth) else 0, 4), "latency_ms_per_reading": round(latency, 5), "confusion_matrix": confusion_matrix(y, predicted, labels=LABELS).tolist(), "per_class": {label: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4), "f1": round(float(f[i]), 4)} for i, label in enumerate(LABELS)}}


def main():
    source = PreparedSource()
    bounds = split_bounds(source.total_frames)
    engine = TrustEngine(source.policy)
    history = defaultdict(lambda: deque(maxlen=60))
    normal = []
    for sequence in range(*bounds["train"]):
        safe = [item.model_input() for item in source.read_frame(sequence)]
        frame = {(item["station_id"], item["variable"]): item for item in safe}
        for item in safe:
            feature = engine.features(item, frame, history, source.stations)
            if len(feature.get("values", [])) >= 24 and item["value"] is not None:
                normal.append(engine.model_features(feature, item["variable"]))
            history[(item["station_id"], item["variable"])].append({**item, "residual": feature.get("residual")})
    engine.model = IsolationForest(n_estimators=80, contamination=.02, random_state=26073, n_jobs=1).fit(normal)
    datasets = {name: build_dataset(source, engine, *span) for name, span in bounds.items()}
    X_train, y_train = datasets["train"]
    X_val, y_val = datasets["validation"]
    X_test, y_test = datasets["test"]
    candidates = {"RandomForest": RandomForestClassifier(n_estimators=90, min_samples_leaf=2, class_weight="balanced_subsample", random_state=26073, n_jobs=1), "ExtraTrees": ExtraTreesClassifier(n_estimators=100, min_samples_leaf=2, class_weight="balanced", random_state=26073, n_jobs=1)}
    comparisons = {}
    for name, candidate in candidates.items():
        candidate.fit(X_train, y_train)
        comparisons[name] = evaluate(candidate, X_val, y_val)
    def rank(name):
        result = comparisons[name]
        return result["macro_f1"] + .3 * result["strict_fault_recall"] - .4 * result["false_alarm_rate"] - .01 * result["latency_ms_per_reading"]
    chosen = max(candidates, key=rank)
    held_out = evaluate(candidates[chosen], X_test, y_test)
    out = ROOT / "artifacts/demo_v1"
    out.mkdir(parents=True, exist_ok=True)
    isolation, classifier = out / "isolation_forest.joblib", out / "fault_classifier.joblib"
    joblib.dump(engine.model, isolation, compress=3)
    joblib.dump({"model": candidates[chosen], "features": CLASSIFIER_FEATURES}, classifier, compress=3)
    (out / "policy.json").write_text(json.dumps(source.policy, indent=2) + "\n", encoding="utf-8")
    (out / "feature_config.json").write_text(json.dumps({"feature_order": CLASSIFIER_FEATURES, "isolation_features": ["absolute_step_scaled", "absolute_expected_residual_scaled", "absolute_spatial_residual_scaled", "repeat_run_scaled"]}, indent=2) + "\n", encoding="utf-8")
    manifest = {"model_version": "hybrid-2.0", "model_type": f"IsolationForest + {chosen}", "trained_at": now(), "dataset_id": source.manifest["dataset_id"], "source_name": source.manifest["source_name"], "provenance_type": source.manifest["provenance_type"], "labels": LABELS, "label_origin": "Fault labels are deterministic simulated transformations of historical gridded observations; no physical failure labels exist.", "feature_order": CLASSIFIER_FEATURES, "chronological_split_boundaries": {name: {"start_sequence": span[0], "end_sequence_exclusive": span[1], "start_timestamp": source.frames[span[0]][0]["timestamp"], "end_timestamp": source.frames[span[1]-1][0]["timestamp"]} for name, span in bounds.items()}, "sample_counts": {name: {label: int(np.sum(y == label)) for label in LABELS} for name, (_, y) in datasets.items()}, "candidate_validation_metrics": comparisons, "chosen_model": chosen, "held_out_metrics": held_out, "artifact_hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (isolation, classifier)}, "artifact_bytes": {path.name: path.stat().st_size for path in (isolation, classifier)}, "python": platform.python_version(), "scikit_learn": sklearn.__version__, "limitations": "One gridded historical window with simulated labels. Held-out period is chronological but shares geography and injection design; metrics do not measure physical AWS field accuracy."}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"chosen_model": chosen, "samples": manifest["sample_counts"], "held_out_macro_f1": held_out["macro_f1"], "held_out_fault_recall": held_out["strict_fault_recall"], "held_out_false_alarm_rate": held_out["false_alarm_rate"]}))


if __name__ == "__main__":
    main()
