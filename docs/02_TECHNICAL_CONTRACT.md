# AtmoTrust — Technical Contract

> Autonomous build edition · Machine contract `2.0.0` · 19 September 2026  
> Governing scope: `01_PROJECT_MASTER.md`

This file freezes the public boundaries required for one coherent implementation. Codex may improve private internals while preserving these semantics.

## 1. Approved implementation

| Layer | Required choice |
|---|---|
| Frontend | React + Vite + TypeScript |
| Styling | Plain CSS or the repository's already-working Tailwind setup; do not migrate a working UI |
| Backend | FastAPI + Pydantic + Uvicorn |
| Data/ML | Pandas + NumPy + scikit-learn + joblib |
| Charts | Plotly if already configured; otherwise a small maintained React chart library |
| Map | Leaflet with a non-tile fallback |
| Real time | Native WebSocket |
| Persistence | SQLite for runs/incidents/actions; memory for the active replay clock |
| Tests | Pytest and the existing frontend test runner; Playwright only if already available or quick to add |
| Deployment | Existing repository target first; otherwise Vercel frontend + Render backend configuration |

Use one backend service and one frontend application. Do not add microservices, Redis, Celery, Supabase, or a second state system.

## 2. Repository target

Adapt to useful code already present. If the repository is empty or inconsistent, converge on:

```text
atmotrust/
  docs/                         # the six governing MD files + reports
  backend/
    app/
      api/
      core/
      ingestion/
      replay/
      simulation/
      features/
      models/
      trust_engine/
      health/
      operations/
      storage/
      main.py
    tests/
    requirements.txt
  frontend/
    src/
      app/
      pages/
      components/
      services/
      types/
      styles/
    package.json
  data/
    raw/                        # gitignored when large
    prepared/demo_v1/
  artifacts/demo_v1/
  benchmarks/
  scripts/
  .env.example
  README.md
```

Do not create duplicate `frontend-v2`, `final-backend`, or parallel app trees. Consolidate the best existing implementation into one runnable path.

## 3. System invariants

1. The backend is the single source of truth.
2. Every client joins the same selected `run_id`.
3. The frontend never computes analytical outputs.
4. Fault injection transforms copied observations; source values and provenance remain preserved.
5. Model input excludes injection metadata, scenario labels, preserved clean values, and benchmark labels.
6. Replay and live observations share one normalized schema.
7. WebSocket updates come from committed backend state, not random browser timers.
8. Each reset creates a new `generation`; clients reject older-generation updates.
9. Frame processing is atomic across stations.
10. No score, alert, diagnosis, or benchmark result is hard-coded for the demo.

## 4. Canonical fields

### Variables and units

| Variable | Field | Unit |
|---|---|---|
| Temperature | `temperature_c` | °C |
| Atmospheric pressure | `pressure_hpa` | hPa |
| Relative humidity | `humidity_pct` | % |

Use one pressure reference consistently within a peer group. Store timestamps as ISO-8601 UTC.

### Enums

```text
Variable         = temperature_c | pressure_hpa | humidity_pct
SourceMode       = replay | live
RunStatus        = preparing | paused | running | completed | degraded | failed
Decision         = likely_fault | needs_review | likely_genuine
TrustBand        = low | uncertain | high | very_high
Severity         = none | low | medium | high | critical
FaultType        = spike | freeze | drift | bias | noise | missing | unknown
IncidentStatus   = open | acknowledged | confirmed_genuine | confirmed_fault | resolved
AssessmentStatus = complete | insufficient_context | missing | invalid | model_unavailable
```

Friendly UI labels may differ, but API enum values do not.

## 5. Shared data shapes

Pydantic models are the backend authority. Matching TypeScript interfaces must use the same fields and nullability.

### Observation

```json
{
  "sample_id": "string",
  "run_id": "string",
  "generation": 1,
  "sequence": 42,
  "station_id": "CHD-01",
  "timestamp": "ISO-8601 UTC",
  "variable": "temperature_c",
  "value": 27.4,
  "unit": "°C",
  "source_mode": "replay",
  "source_name": "prepared_demo_v1",
  "source_timestamp": "ISO-8601 UTC",
  "received_at": "ISO-8601 UTC",
  "is_test_overlay": false,
  "raw_value": 27.4
}
```

`value` and `raw_value` may be null for missing data. Before inference, project this to a model-safe shape that excludes `raw_value`, `is_test_overlay`, injection IDs, scenario names, and labels.

### Evidence item

```json
{
  "kind": "spatial",
  "label": "Nearby stations disagree",
  "detail": "Four usable peers stayed within their expected ranges.",
  "support": -0.82,
  "available": true
}
```

`support` ranges from -1 (fault evidence) to +1 (genuine evidence).

### Assessment

```json
{
  "sample_id": "string",
  "station_id": "CHD-01",
  "variable": "temperature_c",
  "timestamp": "ISO-8601 UTC",
  "assessment_status": "complete",
  "trust_score": 24,
  "trust_band": "low",
  "decision": "likely_fault",
  "confidence": 0.86,
  "severity": "high",
  "fault_type": "spike",
  "expected_value": 28.1,
  "evidence": []
}
```

`trust_score`, `trust_band`, and `expected_value` may be null. Confidence is evidence confidence, not prediction accuracy.

### Sensor health

```json
{
  "station_id": "CHD-01",
  "variable": "temperature_c",
  "health_score": 63,
  "health_status": "watch",
  "maintenance_priority": 72,
  "recommendation": "Inspect calibration and recent drift.",
  "updated_at": "ISO-8601 UTC"
}
```

### State payload

```json
{
  "contract_version": "2.0.0",
  "run_id": "string",
  "generation": 1,
  "state_version": 120,
  "status": "running",
  "speed": 10,
  "source_mode": "replay",
  "stations": [],
  "recent_observations": [],
  "latest_assessments": [],
  "active_incidents": [],
  "maintenance_items": [],
  "active_injections": [],
  "source_status": []
}
```

## 6. Score and state invariants

| Score | Band | Decision |
|---:|---|---|
| 0–34 | `low` | `likely_fault` |
| 35–64 | `uncertain` | `needs_review` |
| 65–84 | `high` | `likely_genuine` |
| 85–100 | `very_high` | `likely_genuine` |

- The backend returns band and decision; the frontend does not repeat the thresholds.
- Insufficient evidence returns `trust_score=null` and a reason.
- Missing delivery may create an incident without a numeric observation score.
- Health and maintenance priority are separate 0–100 values.
- Overall station status is derived by the backend from latest assessments and source availability.

## 7. Atomic frame processing

For each replay frame or accepted live batch:

1. read and normalize source observations;
2. preserve provenance and raw values;
3. apply an active regional transformation;
4. apply independent sensor-fault transformations;
5. build causal history and peer context using current/past data only;
6. analyze all station-variable observations;
7. update health, incidents, maintenance ranking, and operator history;
8. persist the committed frame;
9. increment `state_version`;
10. publish one WebSocket update.

Clients must never observe half of one frame and half of another.

## 8. Public Python boundaries

```python
PreparedSource.read_frame(sequence: int) -> list[Observation]
LiveAdapter.fetch_latest() -> tuple[list[Observation], SourceStatus]
ScenarioInjector.apply(observations, active_injections, regional_event, sequence) -> list[Observation]
TrustEngine.analyze_frame(model_observations, history, stations, policy) -> list[Assessment]
HealthEngine.update(assessments, previous_health, incidents, policy) -> list[SensorHealth]
RunController.snapshot(run_id: str) -> StatePayload
```

Internal class names may change, but API, simulation, analysis, and health responsibilities stay separated enough to test independently.

## 9. REST API

All application routes use `/api/v1` and JSON.

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | readiness, build, and contract version |
| `GET` | `/catalog` | stations, sources, variables, and supported scenarios |
| `POST` | `/runs` | create/resettable demo run and return `run_id` |
| `GET` | `/runs/{run_id}/state` | reconnect snapshot |
| `GET` | `/runs/{run_id}/history` | bounded chart history |
| `POST` | `/runs/{run_id}/commands` | play, pause, reset, set speed, or change source |
| `POST` | `/runs/{run_id}/injections/batch` | validate and schedule 1–8 faults atomically |
| `DELETE` | `/runs/{run_id}/injections/{injection_id}` | cancel scheduled/active fault |
| `POST` | `/runs/{run_id}/regional-events` | start approved replay scenario |
| `POST` | `/runs/{run_id}/incidents/{incident_id}/actions` | acknowledge, confirm, or resolve |

Authentication is out of scope for the competition build. Validate every mutation and rate-limit obvious accidental command flooding in process.

### Command body

```json
{ "command": "set_speed", "speed": 10, "command_id": "client-id" }
```

Supported speeds are `1`, `10`, and `60`.

### Injection spec

```json
{
  "station_id": "CHD-01",
  "variable": "temperature_c",
  "fault_type": "spike",
  "magnitude": 8.0,
  "duration_samples": 3
}
```

The backend validates station, variable, fault type, safe magnitude, duration, and conflicts. A batch begins on one shared next-frame boundary. Injection requests never contain scores or diagnoses.

## 10. WebSocket contract

```text
/api/v1/runs/{run_id}/ws?contract_version=2.0.0
```

Message types: `snapshot`, `update`, `reset`, `heartbeat`, and `error`.

Each message includes `run_id`, `generation`, `state_version`, `type`, and `sent_at`.

Client behaviour:

- reject an older generation;
- ignore duplicate or older state versions;
- reconnect with bounded exponential backoff;
- fetch a fresh snapshot after reconnect;
- deduplicate chart points by generation, station, variable, source mode, and sequence.

## 11. Replay and simulation semantics

- Speed changes wall-clock scheduling, not source timestamps.
- Pause completes the current atomic frame and then stops.
- Reset clears run-derived incidents, actions, history, and injections; increments generation; and reloads warm-up context.
- Spike adds a short abrupt offset.
- Freeze repeats the last valid value.
- Drift adds a progressive signed offset.
- Bias adds a fixed offset and may represent an unrealistic value.
- Noise adds deterministic seeded variation.
- Missing supplies no usable value for the selected slots.
- A regional event changes several stations coherently before independent faults are applied.
- Live overlays operate on preserved copies and never mutate upstream data.
- Randomness uses a run seed so the same schedule is reproducible.

## 12. Persistence

SQLite requires only:

```text
runs
observations
assessments
sensor_health
incidents
operator_actions
injections
```

Use parameterized SQL and short transactions. Active clocks and WebSocket connections live in memory. A restart may terminate disposable demo runs; the UI must say so clearly.

### Practical scalability

- Load stations and peer relationships from metadata rather than hard-coding logic per station.
- Process one atomic frame as a batch and reuse computed rolling summaries.
- Bound in-memory chart/history windows and WebSocket payloads.
- Keep models lightweight and record mean/p95 frame latency.
- The single-process prototype is the supported competition deployment; document later horizontal scaling as future work rather than pretending it is already implemented.

## 13. Environment configuration

```text
ATMOTRUST_ENV=development|hosted|local_demo
ATMOTRUST_DATABASE_PATH=
ATMOTRUST_DATA_DIR=
ATMOTRUST_ARTIFACT_DIR=
ATMOTRUST_ALLOWED_ORIGINS=
ATMOTRUST_LIVE_PROVIDER=open_meteo|disabled
ATMOTRUST_FRONTEND_ORIGIN=
ATMOTRUST_LOG_LEVEL=INFO
VITE_API_BASE_URL=
VITE_WS_BASE_URL=
```

`.env.example` contains safe examples only. The app must have repository-relative local defaults.

## 14. Error behaviour

- Invalid input: `422` with useful field detail.
- Unknown run/resource: `404`.
- Invalid run state or conflicting fault: `409`.
- Rate/capacity limit: `429`.
- Live source or model unavailable: `503` where appropriate plus an honest degraded state.
- Unexpected failure: `500` with request ID and no client-side stack trace.

One bad station row must never silently become healthy. Return an explicit invalid/unavailable result while processing other stations safely.

## 15. Release tests

The final build must pass:

1. Clean backend and frontend installation.
2. Create, play, pause, set speed, and reset.
3. Two clients receive the same run and monotonic state versions.
4. A spike creates a backend assessment, alert, evidence, and maintenance item.
5. Two simultaneous faults begin on the same boundary.
6. Missing data creates a chart gap and a data-loss incident.
7. A regional event is not labelled faulty across the network.
8. A regional event plus one sensor fault isolates the bad sensor.
9. Operator actions persist across navigation and refresh.
10. Reconnect returns a valid snapshot without duplicate points.
11. Live mode shows real provider/source time or an honest unavailable state.
12. The benchmark command finishes and writes measured results.
13. Production build contains no fixture API, random score generator, leaked secret, or hard-coded localhost dependency.
14. A five-minute golden demo can be completed twice after reset.
15. The README and `docs/USE_CASES.md` describe executable use cases and honest limitations.

## 16. Compatible-change rule

Codex may repair a clearly broken or missing field if it updates backend models, TypeScript types, fixtures, tests, and docs together. Prefer compatibility aliases over broad rewrites. Record any unavoidable public deviation in `docs/IMPLEMENTATION_NOTES.md`.
