from .schema import SensorHealth, now


RECOMMEND = {"spike": "Inspect wiring and transient interference.", "freeze": "Check logger, power, and sensor sampling.", "drift": "Inspect calibration and recent drift.", "bias": "Verify calibration and sensor placement.", "noise": "Inspect shielding, cabling, and power quality.", "missing": "Check power, telemetry, and communications.", "unknown": "Inspect sensor and recent telemetry."}
SEVERITY = {"none": 0, "low": 25, "medium": 50, "high": 75, "critical": 100}


class HealthEngine:
    def update(self, assessments, previous_health, incidents, policy=None, criticality=None):
        criticality = criticality or {}
        result = []
        for item in assessments:
            key = (item.station_id, item.variable)
            old = previous_health.get(key)
            if item.assessment_status == "insufficient_context":
                result.append(old.model_copy(update={"updated_at": now()}) if old else SensorHealth(station_id=item.station_id, variable=item.variable, updated_at=now()))
                continue
            if item.assessment_status == "missing":
                burden = 0.85
            elif item.decision == "likely_fault":
                burden = min(1, 0.5 + item.confidence * SEVERITY[item.severity] / 180)
            elif item.decision == "needs_review":
                burden = 0.15 * item.confidence
            else:
                burden = 0
            old_burden = 1 - old.health_score / 100 if old and old.health_score is not None else 0
            alpha = 0.38 if burden > old_burden else 0.06
            next_burden = alpha * burden + (1 - alpha) * old_burden
            score = round(100 * (1 - next_burden))
            trend = ((old.trend if old else []) + [score])[-24:]
            status = "healthy" if score >= 80 else "watch" if score >= 55 else "degrading"
            related = next((incident for incident in incidents if incident.station_id == item.station_id and incident.variable == item.variable and incident.status in ("open", "acknowledged", "confirmed_fault")), None)
            duration = related.duration_samples if related else 0
            priority = round(0.30 * (100 - score) + 0.25 * SEVERITY[item.severity] + 0.20 * min(100, duration * 12) + 0.15 * item.confidence * 100 + 0.10 * 100 * criticality.get(item.station_id, 0.5)) if related else 0
            result.append(SensorHealth(station_id=item.station_id, variable=item.variable, health_score=score, health_status=status, maintenance_priority=priority, recommendation=RECOMMEND[item.fault_type] if related else "Continue routine monitoring.", updated_at=now(), trend=trend))
        return result
