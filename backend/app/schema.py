from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

Variable = Literal["temperature_c", "pressure_hpa", "humidity_pct"]
FaultType = Literal["spike", "freeze", "drift", "bias", "noise", "missing"]
UNITS = {"temperature_c": "°C", "pressure_hpa": "hPa", "humidity_pct": "%"}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Observation(BaseModel):
    sample_id: str
    run_id: str
    generation: int
    sequence: int
    station_id: str
    timestamp: str
    variable: Variable
    value: float | None
    unit: str
    source_mode: Literal["replay", "live"]
    source_name: str
    source_timestamp: str
    received_at: str
    is_test_overlay: bool = False
    raw_value: float | None = None

    def model_input(self):
        return {key: getattr(self, key) for key in ("sample_id", "station_id", "variable", "value", "timestamp", "sequence")}


class Evidence(BaseModel):
    kind: str
    label: str
    detail: str
    support: float
    available: bool = True


class Assessment(BaseModel):
    sample_id: str
    station_id: str
    variable: Variable
    timestamp: str
    assessment_status: Literal["complete", "insufficient_context", "missing", "invalid", "model_unavailable"]
    trust_score: int | None = None
    trust_band: Literal["low", "uncertain", "high", "very_high"] | None = None
    decision: Literal["likely_fault", "needs_review", "likely_genuine"] = "needs_review"
    confidence: float = 0
    severity: Literal["none", "low", "medium", "high", "critical"] = "none"
    fault_type: Literal["spike", "freeze", "drift", "bias", "noise", "missing", "unknown"] = "unknown"
    expected_value: float | None = None
    peer_value: float | None = None
    observed_value: float | None = None
    explanation: str = ""
    resolution: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class SensorHealth(BaseModel):
    station_id: str
    variable: Variable
    health_score: int | None = None
    health_status: Literal["healthy", "watch", "degrading", "unknown"] = "unknown"
    maintenance_priority: int = 0
    recommendation: str = "Await sufficient observations."
    updated_at: str
    trend: list[int] = Field(default_factory=list)


class InjectionSpec(BaseModel):
    station_id: str
    variable: Variable
    fault_type: FaultType
    magnitude: float = Field(default=8, ge=-50, le=50)
    duration_samples: int = Field(default=3, ge=1, le=24)


class Injection(InjectionSpec):
    injection_id: str
    start_sequence: int
    end_sequence: int
    status: Literal["scheduled", "active", "completed", "cancelled"] = "scheduled"
    remaining_samples: int = 0


class Incident(BaseModel):
    incident_id: str
    station_id: str
    variable: Variable
    opened_at: str
    last_seen_at: str
    status: Literal["open", "acknowledged", "confirmed_genuine", "confirmed_fault", "resolved"] = "open"
    fault_type: str
    severity: str
    confidence: float
    duration_samples: int = 1
    maintenance_priority: int = 0
    health_score: int | None = None
    recommendation: str = "Inspect sensor and recent telemetry."
    task_status: str = "Assigned"
    assignee_id: str | None = None


class Action(BaseModel):
    action_id: str
    incident_id: str
    action: Literal["acknowledge", "confirm_genuine", "confirm_fault", "maintenance_complete"]
    timestamp: str


class SourceStatus(BaseModel):
    source_mode: Literal["replay", "live"]
    source_name: str
    provenance_type: str
    status: Literal["available", "unavailable"]
    source_timestamp: str | None = None
    fetched_at: str | None = None
    detail: str = ""
    variables: list[Variable] = Field(default_factory=lambda: list(UNITS))


class Command(BaseModel):
    command: Literal["play", "pause", "reset", "set_speed", "set_source", "step"]
    speed: Literal[1, 10, 60] | None = None
    source_mode: Literal["replay", "live"] | None = None
    command_id: str | None = None


class StatePayload(BaseModel):
    contract_version: str = "2.0.0"
    run_id: str
    generation: int
    state_version: int
    status: str
    speed: int
    source_mode: str
    sequence: int
    source_timestamp: str | None
    stations: list[dict]
    recent_observations: list[Observation]
    latest_assessments: list[Assessment]
    recent_assessments: list[Assessment]
    sensor_health: list[SensorHealth]
    active_incidents: list[Incident]
    maintenance_items: list[Incident]
    active_injections: list[Injection]
    regional_event: dict | None
    source_status: list[SourceStatus]
    operator_actions: list[Action]
