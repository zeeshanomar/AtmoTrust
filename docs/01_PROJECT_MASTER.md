# AtmoTrust — Project Master

> Autonomous build edition · 19 September 2026  
> Problem Statement: SIH26073  
> Team: Soul Society

## 1. Mission

Build a complete, executable software prototype that detects and explains anomalies in Automatic Weather Station data using only:

- temperature in °C;
- atmospheric pressure in hPa;
- relative humidity in %.

AtmoTrust must distinguish genuine regional weather changes from isolated sensor or communication faults. It must turn every result into an operator-friendly Trust Score, decision, evidence, Sensor Health status, and maintenance recommendation.

This repository is to be completed by one autonomous Codex run. There is no member-wise implementation, manual integration, PR choreography, or waiting for human review between stages.

## 2. Product promise

For every incoming observation, AtmoTrust asks:

1. Is the value physically possible?
2. Is it unusual compared with this sensor's recent history?
3. Do nearby stations show the same change?
4. Are temperature, pressure, and humidity moving consistently?
5. Does the learned normal pattern support the observation?

The answer must be visible in plain language. “Unusual” must never automatically mean “faulty.”

## 3. Winning judge story

The finished demo must prove this sequence:

1. Five stations stream moving Temperature, Pressure, and Humidity data.
2. The judge injects a spike, freeze, drift, bias, noise, or missing-data fault.
3. The Command Centre changes immediately from the real backend result.
4. Station Investigation explains the temporal, spatial, and multivariate evidence.
5. Maintenance Centre shows the operational consequence and recommended action.
6. A regional weather event moves several stations coherently and remains mostly genuine.
7. An independent bad sensor inside that regional event is still isolated.
8. A genuine live-data lane shows its provider and timestamps, or an honest unavailable state.

The reliable historical replay is the primary demonstration. Live-provider availability must never control whether the demo succeeds.

## 4. Non-negotiable final scope

### 4.1 Must work end to end

- Five prepared stations in the Chandigarh–Punjab–Haryana region.
- A deterministic replay with play, pause, reset, and 1×/10×/60× speed.
- Moving Temperature, Pressure, and Humidity charts.
- Six injected patterns: spike, freeze, drift, bias/unrealistic value, noise, and missing/data loss.
- A single batch containing multiple simultaneous faults.
- One coherent regional-weather scenario.
- A regional-weather scenario combined with one independent sensor fault.
- Observation Trust Score, decision, confidence, severity, probable fault type, and measured evidence.
- Sensor Health Index, maintenance priority, recommendation, and operator actions.
- Four synchronized screens: Command Centre, Station Investigation, Maintenance Centre, and Simulation Lab.
- Two browser windows connected to the same backend state.
- One genuine live-source adapter with truthful degraded behaviour.
- Automated tests, a measured benchmark, setup instructions, and a one-command local start path.
- A concise use-case document covering all six faults, regional weather, and the compound scenario.
- A production build with no mock analytics or localhost-only frontend URL.

### 4.2 Add only after the core passes

- Suggested corrected value with an uncertainty warning.
- Extra benchmark charts.
- SHAP/LIME views if they improve the explanation without destabilizing the build.
- Additional live providers or visual polish.

An unfinished optional feature must be removed or hidden.

### 4.3 Out of scope

- Wind, rainfall, AQI, radar, satellite, or forecast-model values as detector inputs.
- Hardware or ESP32 implementation.
- Authentication, user roles, billing, notifications, or a mobile app.
- Microservices, Redis, queues, blockchain, Kubernetes, or architecture added for appearance.
- Claims of nationwide scale, self-healing hardware, or accuracy that has not been measured.

## 5. System shape

```text
Prepared historical replay ─┐
                            ├─> normalization -> scenario/fault transforms
Genuine live adapter ───────┘                  -> contextual evidence engine
                                                -> trust + fault classification
                                                -> sensor health + incidents
                                                -> REST/WebSocket shared state
                                                -> four synchronized screens
```

The backend is the only analytical authority. The frontend displays results and submits commands; it does not calculate scores, diagnoses, station colours, health, or maintenance ranking.

The competition build uses small statistical/ML models, bounded history, batched frame processing, and no runtime LLM. This keeps latency and energy use modest while leaving the station registry and peer graph data-driven for future larger networks.

## 6. Trust and operational outputs

The Observation Trust Score is a 0–100 evidence score, not a probability.

| Score | UI label | Backend decision |
|---:|---|---|
| 0–34 | Likely Fault | `likely_fault` |
| 35–64 | Needs Review | `needs_review` |
| 65–84 | Likely Genuine | `likely_genuine` |
| 85–100 | Extremely Trustworthy | `likely_genuine` |

Keep these concepts separate:

- Trust Score: reliability of the current observation.
- Confidence: evidence availability, strength, and agreement.
- Severity: operational impact if the observation is faulty.
- Fault type: best-supported failure pattern.
- Sensor Health: longer-term behaviour of one station-variable pair.
- Maintenance priority: which active issue should be handled first.

If there is not enough context, show `N/A` and explain what is missing. A missing observation may create an incident without pretending that a numeric score exists.

## 7. Demonstration station network

Use these logical station nodes unless verified source metadata in the repository already defines a better five-station cluster:

| ID | Display name | Latitude | Longitude |
|---|---|---:|---:|
| `CHD-01` | Chandigarh | 30.7333 | 76.7794 |
| `MOH-01` | Mohali | 30.7046 | 76.7179 |
| `PKL-01` | Panchkula | 30.6942 | 76.8606 |
| `AMB-01` | Ambala | 30.3782 | 76.7767 |
| `PTA-01` | Patiala | 30.3398 | 76.3869 |

These are software demonstration nodes. Provider and provenance labels must say whether data came from a physical station feed, a gridded location feed, or a prepared demonstration dataset.

## 8. Four product screens

### Command Centre

- network summary and source/run status;
- station map with an offline fallback;
- moving T/P/RH charts;
- latest states, incidents, and maintenance preview;
- quick navigation to a station investigation.

### Station Investigation

- station and variable selector;
- observed, expected, and peer trend;
- Trust Score, decision, confidence, severity, and probable fault;
- two to four evidence cards using measured values;
- Acknowledge, Confirm Genuine, and Confirm Fault actions.

### Maintenance Centre

- ranked active issues;
- Sensor Health and recent trend;
- recommendation and incident history;
- Maintenance Complete action.

### Simulation Lab

- replay controls and source selection;
- multi-fault batch builder;
- station, variable, fault type, magnitude, and duration controls;
- active-injection list and cancellation;
- regional weather event control.

## 9. Truthfulness rules

- Inference must never receive the injection label, scenario name, preserved clean value, or benchmark target.
- A “live” label is used only for data fetched from an external provider during the current session.
- Synthetic or transformed values are explicitly labelled as demonstration/test data.
- No hard-coded Trust Scores, alerts, benchmark metrics, or station states.
- Missing data is a gap or `N/A`, never zero.
- If a model or live provider fails, show a degraded state instead of substituting a fake success.

## 10. Definition of done

The project is complete only when all of the following are true:

- fresh setup instructions work from the repository root;
- backend and frontend production builds succeed;
- all release tests in `02_TECHNICAL_CONTRACT.md` pass;
- all four screens use the same real state;
- two clients stay synchronized;
- every required scenario can be reset and repeated;
- the benchmark is generated from the implemented pipeline;
- no secret, local absolute path, generated junk, or hidden mock remains;
- the README explains architecture, commands, demo flow, data provenance, metrics, and limitations;
- `docs/USE_CASES.md` explains the required operational scenarios;
- deployment is attempted when credentials/configuration already exist, while local execution remains fully functional.

## 11. Priority rule

When time or tooling is constrained, protect this order:

1. working end-to-end replay and real analysis;
2. fault injection, regional context, and synchronized UI;
3. explanations, incidents, and maintenance workflow;
4. tests, reproducibility, and local start path;
5. measured benchmark and live lane;
6. deployment and visual polish;
7. optional features.

A smaller real system beats a larger fake one.
