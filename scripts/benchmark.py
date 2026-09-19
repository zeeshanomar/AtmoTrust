"""Held-out chronological injection benchmark using the runtime engine and policy."""
import csv
import json
import statistics
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
import numpy as np
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.analysis import BOUNDS, SCALE, TrustEngine
from app.data import PreparedSource
from app.schema import Injection
from app.simulation import ScenarioInjector


def metrics(truth, prediction):
    tp = sum(t and p for t, p in zip(truth, prediction))
    fp = sum(not t and p for t, p in zip(truth, prediction))
    fn = sum(t and not p for t, p in zip(truth, prediction))
    tn = sum(not t and not p for t, p in zip(truth, prediction))
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0, "false_alarm_rate": round(fp / (fp + tn), 4) if fp + tn else 0}


def evaluate(source, engine, name, fault=None, regional=False):
    start = int(source.total_frames * 0.85) + 52
    history = defaultdict(lambda: deque(maxlen=60))
    injector = ScenarioInjector()
    rows, latencies = [], []
    duration = 1 if fault == "spike" else 6
    injection = Injection(station_id="CHD-01", variable="temperature_c", fault_type=fault, magnitude={"spike": 9, "freeze": 0, "drift": 12, "bias": 9, "noise": 9, "missing": 0}.get(fault, 0), duration_samples=duration, injection_id=f"benchmark-{fault}", start_sequence=start + 2, end_sequence=start + 2 + duration) if fault else None
    event = {"start_sequence": start, "end_sequence": start + 12, "duration_samples": 12} if regional else None
    for sequence in range(start - 24, start + 12):
        observations = source.read_frame(sequence, "benchmark", 1)
        if sequence >= start:
            observations = injector.apply(observations, [injection] if injection else [], event, sequence, {(key): values[-1]["value"] for key, values in history.items() if values})
        safe = [item.model_input() for item in observations]
        t0 = time.perf_counter()
        assessments, features = engine.analyze_frame(safe, history, source.stations)
        if sequence >= start:
            latencies.append((time.perf_counter() - t0) * 1000)
            for item, assessment in zip(observations, assessments):
                target = bool(injection and injection.start_sequence <= sequence < injection.end_sequence and item.station_id == injection.station_id and item.variable == injection.variable)
                f = features[(item.station_id, item.variable)]
                direct = item.value is None or (item.value is not None and not BOUNDS[item.variable][0] <= item.value <= BOUNDS[item.variable][1]) or abs(f.get("step") or 0) > 5 * SCALE[item.variable] or f.get("repeated", 0) >= 3
                if engine.model is not None and item.value is not None:
                    model_only = bool(engine.model.predict([engine.model_features(f, item.variable)])[0] == -1)
                else:
                    model_only = False
                rows.append({"episode": name, "sequence": sequence, "station_id": item.station_id, "variable": item.variable, "true_fault": int(target), "true_type": fault if target else "clean", "decision": assessment.decision, "assessment_status": assessment.assessment_status, "predicted_type": assessment.fault_type if assessment.decision != "likely_genuine" or assessment.assessment_status in ("missing", "invalid") else "clean", "trust_score": assessment.trust_score, "physical_only": int(direct), "isolation_forest_only": int(model_only), "full": int(assessment.decision == "likely_fault" or assessment.assessment_status in ("missing", "invalid"))})
        for item in observations:
            feature = features[(item.station_id, item.variable)]
            history[(item.station_id, item.variable)].append({**item.model_input(), "residual": feature.get("residual")})
    return rows, latencies


def main():
    source = PreparedSource()
    artifact = ROOT / "artifacts/demo_v1/isolation_forest.joblib"
    engine = TrustEngine(source.policy, artifact)
    episodes = [("clean", None, False)] + [(fault, fault, False) for fault in ("spike", "freeze", "drift", "bias", "noise", "missing")] + [("regional", None, True), ("regional_compound", "spike", True)]
    rows, latencies = [], []
    for name, fault, regional in episodes:
        episode_rows, times = evaluate(source, engine, name, fault, regional)
        rows.extend(episode_rows)
        latencies.extend(times)
    truth = [bool(row["true_fault"]) for row in rows]
    full = [bool(row["full"]) for row in rows]
    per_fault = {fault: round(sum(row["full"] for row in rows if row["true_type"] == fault) / max(1, sum(row["true_type"] == fault for row in rows)), 4) for fault in ("spike", "freeze", "drift", "bias", "noise", "missing")}
    typed = [row for row in rows if row["true_fault"] and row["full"]]
    labels = ["clean", "spike", "freeze", "drift", "bias", "noise", "missing", "unknown"]
    true_types = [row["true_type"] for row in rows]
    predicted_types = [row["predicted_type"] for row in rows]
    precision, recall, f1, _ = precision_recall_fscore_support(true_types, predicted_types, labels=labels, zero_division=0)
    per_class = {label: {"precision": round(float(precision[i]), 4), "recall": round(float(recall[i]), 4), "f1": round(float(f1[i]), 4)} for i, label in enumerate(labels)}
    classifier_artifact = artifact.with_name("fault_classifier.joblib")
    result = {"dataset_id": source.manifest["dataset_id"], "provenance_type": source.manifest["provenance_type"], "source_name": source.manifest["source_name"], "held_out_start_sequence": int(source.total_frames * 0.85), "episode_start_sequence": int(source.total_frames * 0.85) + 52, "episodes": len(episodes), "evaluated_frames": len(latencies), "evaluated_observations": len(rows), "clean_observations": len(rows)-sum(truth), "fault_observations": sum(truth), "full": metrics(truth, full), "physical_only": metrics(truth, [bool(row["physical_only"]) for row in rows]), "isolation_forest_only": metrics(truth, [bool(row["isolation_forest_only"]) for row in rows]), "per_fault_recall": per_fault, "per_fault_precision_recall_f1": per_class, "multiclass_labels": labels, "multiclass_confusion_matrix": confusion_matrix(true_types, predicted_types, labels=labels).tolist(), "fault_type_macro_f1": round(float(f1_score(true_types, predicted_types, labels=labels[:7], average="macro", zero_division=0)), 4), "detected_fault_type_accuracy": round(sum(row["predicted_type"] == row["true_type"] for row in typed) / len(typed), 4) if typed else 0, "decision_confusion": {key: {decision: sum(row["true_type"] == key and row["decision"] == decision for row in rows) for decision in ("likely_genuine", "needs_review", "likely_fault")} for key in labels[:7]}, "mean_frame_latency_ms": round(statistics.mean(latencies), 2), "p95_frame_latency_ms": round(float(np.percentile(latencies, 95)), 2), "model_artifact_bytes": sum(path.stat().st_size for path in (artifact, classifier_artifact) if path.exists()), "limitations": "Injected episodes on later chronological frames not used for training; repeated clean context across episodes. Labels are simulated, not observed physical sensor failures. Shared geography and earlier rule tuning limit external validity."}
    out = ROOT / "benchmarks/results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (out / "observations.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (out / "summary.md").write_text(f"# Chronological injected-fault benchmark\n\nSource: `{result['source_name']}` ({result['provenance_type']}). {len(episodes)} episodes, {len(latencies)} frames, {len(rows)} observations, {sum(truth)} injected fault slots.\n\n| Method | Precision | Recall | F1 | False alarm rate |\n|---|---:|---:|---:|---:|\n" + "\n".join(f"| {name} | {result[name]['precision']:.3f} | {result[name]['recall']:.3f} | {result[name]['f1']:.3f} | {result[name]['false_alarm_rate']:.3f} |" for name in ("physical_only", "isolation_forest_only", "full")) + f"\n\nPer-fault precision/recall/F1: {per_class}. Type macro-F1: {result['fault_type_macro_f1']:.3f}. Mean/p95 frame analysis latency: {result['mean_frame_latency_ms']:.2f}/{result['p95_frame_latency_ms']:.2f} ms. Model size: {result['model_artifact_bytes']} bytes.\n\n{result['limitations']}\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("evaluated_observations", "fault_observations", "full", "per_fault_recall", "mean_frame_latency_ms", "p95_frame_latency_ms")}))


if __name__ == "__main__":
    main()
