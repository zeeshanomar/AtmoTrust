# AtmoTrust — Data and AI Plan

> Autonomous build edition · 19 September 2026  
> Governing contract: `02_TECHNICAL_CONTRACT.md`

The goal is a credible hybrid detector that works end to end. Prefer understandable statistical and ML evidence over a large collection of half-integrated models.

## 1. Fixed analytical scope

The detector may use only these measurements:

- `temperature_c`;
- `pressure_hpa`;
- `humidity_pct`.

Allowed context metadata: timestamp, station identity, coordinates/elevation, source, cadence, and causal historical summaries. Do not use wind, rainfall, AQI, radar, satellite, or forecast-model values as inference features.

## 2. Source strategy

Use this order without stopping for human input:

1. Inspect and reuse any verified T/P/RH datasets already in the repository.
2. Otherwise fetch a compact public historical window for the five specified locations. A no-key provider such as Open-Meteo Archive is acceptable when its provenance is labelled as a gridded/location feed rather than a physical AWS observation.
3. Prepare and commit a small deterministic `demo_v1` dataset containing warm-up plus the demonstration window.
4. If network access is blocked and no data exists, generate a deterministic physically plausible baseline strictly as a last-resort fallback, label it `synthetic_demo`, and expose that limitation in the UI and README. Do not call it historical or live data.

The build must remain runnable offline after preparation.

### Genuine live lane

Implement one adapter for a no-key current-weather provider that exposes all three required variables. Open-Meteo current weather is an acceptable default. The UI must display:

- provider name;
- location/coordinates;
- provider observation timestamp;
- local fetch timestamp;
- available variables;
- whether values are original live readings or test-overlay copies.

On timeout, schema change, or network failure, return a structured unavailable/degraded status. Never replace live data with replay values under a live label.

## 3. Prepared data package

```text
data/prepared/demo_v1/
  observations.csv
  stations.json
  peer_links.json
  policy.json
  manifest.json
  data_report.md
```

`manifest.json` records source URL/provider, retrieval time, date range, units, cadence, row count, missingness, pressure reference, provenance type, and file hashes.

Preparation rules:

1. Convert timestamps to UTC.
2. Convert values to °C, hPa, and %.
3. Preserve missing values; never convert them to zero.
4. Deduplicate by station, variable, and source timestamp.
5. Use one documented cadence and pressure reference.
6. Never invent higher-frequency measurements by blind upsampling.
7. Keep raw data outside inference and small prepared data inside the reproducible demo package.
8. Validate physical ranges and minimum overlap before selecting the window.

## 4. Chronological evaluation

For a sufficiently long historical dataset, split by time:

```text
earliest 70% -> training
next 15%     -> validation
latest 15%   -> final test
```

- Fit scalers, baselines, normal ranges, and Isolation Forest on training data only.
- Select thresholds and fusion settings on validation data.
- Report final metrics on held-out test data.
- Generate independent injected-fault episodes inside each split after splitting.
- Do not use future observations to classify earlier observations.
- Clean values and injection labels are evaluation truth only, never model features.

If the available public window is too small for a defensible model split, use a simpler robust baseline, state the limitation, and still evaluate on later held-out frames. Never manufacture a large accuracy number.

## 5. Runtime evidence pipeline

Each available component returns:

```text
support in [-1, +1]
-1 = strong fault evidence
 0 = inconclusive
+1 = strong genuine/consistent evidence
```

Initial weights:

| Component | Weight | Minimum implementation |
|---|---:|---|
| Physical/direct checks | 0.15 | validity, missing, bounds, one-step jump, repeated values |
| Temporal context | 0.20 | causal rolling median/MAD, variance, deltas, run length, slopes |
| Expected-value residual | 0.20 | robust rolling baseline or validated regressor |
| Spatial context | 0.20 | target-versus-peer residual agreement |
| Multivariate consistency | 0.15 | learned T/P/RH residual or covariance consistency |
| Isolation Forest | 0.10 | anomaly evidence from causal features |

Weights must sum to 1.00 and live in `policy.json`. Do not include an unavailable component in the denominator.

### 5.1 Physical/direct checks

- invalid or non-numeric value;
- humidity outside 0–100%;
- conservative temperature/pressure sanity bounds;
- missing delivery;
- abrupt step consistent with spike;
- identical run consistent with freeze.

Bounds are safeguards, not the complete detector.

### 5.2 Temporal context

Use the selected sensor's current and previous values only:

- one-step and multi-step differences;
- rolling median and median absolute deviation;
- rolling variance;
- identical-value run length;
- short and long causal slopes;
- hour-of-day and day-of-year encodings when history supports them.

### 5.3 Expected-value residual

Start with a robust causal rolling/seasonal baseline. Add one small scikit-learn regressor per variable only if it measurably improves validation. Suitable inputs include lagged values, rolling summaries, time encodings, and current values of the other two variables.

Return:

```text
expected_value
residual = observed - expected
normalized_residual
```

The runtime must not fail merely because an optional regressor artifact is unavailable; it may explicitly use the documented statistical baseline and mark model status accordingly.

### 5.4 Spatial context

- Exclude the target from its peer set.
- Compare standardized residuals rather than raw values where location baselines differ.
- Require at least two usable peers for strong spatial evidence.
- Exclude missing/invalid peers and previously severe unreliable sensors.
- Coherent peer movement supports a genuine regional event.
- Isolated target movement supports a fault.

### 5.5 Multivariate consistency

Compare current T/P/RH movement with relationships learned from clean history. A simple standardized residual/covariance distance is sufficient. Do not add a neural network.

### 5.6 Isolation Forest

Train on normal-reference causal features. Convert `decision_function` output to bounded support using validation percentiles. Isolation Forest contributes evidence; it does not directly set the UI decision.

## 6. Trust fusion

For component weight `w_i`, availability `a_i`, and support `s_i`:

```text
coverage = sum(w_i * a_i)
signed_evidence = sum(w_i * a_i * s_i) / sum(w_i * a_i)
trust_score = clip(round(50 + 50 * signed_evidence), 0, 100)
```

Default minimum evidence coverage for a numeric score:

```text
minimum_evidence_coverage = 0.60
```

At least one context component among temporal, expected, spatial, or multivariate must be available. Otherwise return `trust_score=null`, `decision=needs_review`, and a reason. A confirmed missing delivery follows its incident path without a fake numeric score.

Frozen mapping:

| Score | Band | Decision |
|---:|---|---|
| 0–34 | low | likely_fault |
| 35–64 | uncertain | needs_review |
| 65–84 | high | likely_genuine |
| 85–100 | very_high | likely_genuine |

## 7. Confidence and severity

Confidence combines:

- evidence coverage;
- agreement among available components;
- average absolute evidence strength.

Keep it in `[0, 1]`. It is not “accuracy” or probability of fault.

Severity uses measured magnitude, persistence, spatial disagreement, fault type, and affected variable. Return `none`, `low`, `medium`, `high`, or `critical`. A likely-genuine observation normally has `none` severity.

## 8. Fault simulation and classification

| Fault | Transform | Primary clues |
|---|---|---|
| Spike | abrupt signed offset for 1–3 samples | large delta/residual, peer disagreement |
| Freeze | repeat last valid value | identical run while peers move |
| Drift | progressively increasing/decreasing offset | sustained residual slope |
| Bias | fixed offset, optionally beyond sanity bounds | persistent residual and peer disagreement |
| Noise | seeded high-frequency variation | abnormal rolling variance/instability |
| Missing | null/absent value at expected cadence | delivery gap or communication loss |

Classify these patterns with transparent rules based on measured signatures. A small classifier may break ties only if it is validated and stable.

Use seeded randomness. Store the injection truth outside the model-safe observation. Batch injections are applied on the same replay boundary.

## 9. Regional-weather scenario

The scenario must coherently and gradually transform several station-variable streams, for example:

- a temperature drop;
- a pressure decline;
- a humidity increase;
- small station-specific delays/magnitudes.

The detector sees only the resulting readings and context—not the scenario label.

Expected behaviour:

- peer agreement reduces fault evidence;
- plausible multivariate movement supports genuine weather;
- an independent spike, freeze, drift, bias, noise, or missing sensor remains detectable;
- physical impossibility is never excused merely because several stations move.

## 10. Evidence text

Return the strongest two to four measured evidence items. Use deterministic templates such as:

- “Temperature jumped 8.4°C from the previous sample.”
- “Four usable peers remained near their expected values.”
- “Humidity differs from its expected T/RH relationship by 3.1 standard deviations.”
- “The sensor repeated the same value for 12 samples while peers changed.”

Do not call an LLM at runtime to invent explanations.

## 11. Sensor Health

Health summarizes repeated behaviour for a station-variable pair. Before adequate history, return `null/unknown`.

Maintain an exponentially weighted fault burden:

```text
likely_genuine -> burden 0
needs_review   -> small burden scaled by confidence
likely_fault   -> burden scaled by confidence and severity
health_score   = round(100 * (1 - ewma_burden))
```

Health should decline faster than it recovers.

| Health | Status |
|---:|---|
| 80–100 | healthy |
| 55–79 | watch |
| 0–54 | degrading |
| null | unknown |

## 12. Maintenance priority

Rank active incidents from 0–100 using:

```text
30% health deficit
25% current severity
20% duration/recurrence
15% confidence
10% station criticality
```

Station criticality influences maintenance ordering only; it never changes Trust Score.

## 13. Benchmark

Evaluate injected faults on copies of held-out clean observations. Compare:

1. physical/threshold checks only;
2. Isolation Forest only;
3. full AtmoTrust evidence fusion.

Write machine-readable and human-readable outputs under `benchmarks/results/`.

Required metrics:

- precision, recall, and F1 for strict fault detection;
- false-alarm rate on clean observations;
- per-fault recall;
- three-way decision confusion matrix where meaningful;
- fault-type macro-F1 or accuracy;
- mean and p95 inference latency per frame;
- model artifact size;
- number of evaluated frames and fault episodes.

Do not count every `needs_review` result as correct. Publish the measured values and limitations, even if modest.

## 14. Artifacts and commands

```text
artifacts/demo_v1/
  manifest.json
  isolation_forest.joblib
  expected_temperature.joblib     # only if validated
  expected_pressure.joblib        # only if validated
  expected_humidity.joblib        # only if validated
  feature_config.json
  policy.json
```

Required repository commands or equivalent scripts:

```text
prepare demo data
train/build artifacts
run benchmark
run data/AI tests
```

The artifact manifest records dataset ID, training cutoff, feature order, package versions, hashes, validation choices, benchmark command, and known limitations.

## 15. Data/AI acceptance checklist

- [ ] Only T/P/RH measurements enter inference.
- [ ] Source type, timestamps, units, and pressure reference are documented.
- [ ] No random split, future leakage, clean-value leakage, or injection-label leakage.
- [ ] All six fault transforms are deterministic and tested.
- [ ] Regional and compound scenarios are tested.
- [ ] Trust, confidence, severity, health, and maintenance priority remain distinct.
- [ ] Evidence uses actual measured feature values.
- [ ] Runtime and benchmark use the same policy.
- [ ] Metrics are generated, not typed into the UI.
- [ ] Live data is genuine or explicitly unavailable.
