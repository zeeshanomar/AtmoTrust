# AtmoTrust — UI and Demo Specification

> Autonomous build edition · 19 September 2026  
> Governing contracts: `01_PROJECT_MASTER.md` and `02_TECHNICAL_CONTRACT.md`

The interface should look like a serious weather-network operations product. Judges must understand the state, trigger a fault, and inspect the reasoning without a tutorial.

## 1. Visual direction

- Desktop-first at 1366×768 and 1920×1080; remain usable on tablets.
- Clean technical dashboard, not sci-fi glassmorphism.
- Neutral background and restrained panels.
- Green for genuine/healthy, amber for review/degraded, red for fault/critical, gray for unknown.
- Never use colour alone; pair it with text and icons.
- Use one consistent font family, spacing scale, border radius, and chart treatment.
- Keep headings compact and charts readable.
- Use subtle transitions only for state changes; avoid decorative motion.
- Always show units, source, and timestamps.
- Missing values are chart gaps or `N/A`, never zero.

## 2. Global application shell

Top navigation:

```text
AtmoTrust | Command Centre | Investigation | Maintenance | Simulation Lab
```

A compact persistent status strip shows:

- current run status and speed;
- Replay or Live source mode;
- WebSocket connected/reconnecting/stale state;
- latest source timestamp;
- live-provider status;
- Play/Pause and Reset controls where appropriate.

All pages preserve the same `run_id`, selected station, and connection. Navigation must not create a second run.

The application should create or reuse one demo run automatically on first load so the dashboard does not open into a dead setup screen.

## 3. Command Centre

### Purpose

Answer within ten seconds:

> Which stations are healthy, which need attention, and what is happening now?

### Required layout

1. Four summary cards: monitored stations, likely faults, needs review, open maintenance items.
2. Station map or geographic fallback plus recent alerts.
3. Three moving charts: Temperature, Pressure, Humidity.
4. Compact station table and maintenance preview.

### Map

- Center on the Chandigarh regional cluster.
- Marker shows station label and backend-derived status.
- Selected station is clearly highlighted.
- Popup shows latest T/P/RH, source time, and `View Station`.
- If map tiles fail, retain the same station positions on a simple offline geographic panel; do not leave a blank box.

### Moving charts

- One chart per variable with unit and source-time axis.
- Keep approximately 60 recent points per station.
- Highlight the selected station; mute others without hiding regional context.
- Show missing values as gaps.
- Mark test-overlay points discreetly.
- Do not generate browser-side data while waiting for the backend.

### Alerts

Each alert shows station, variable, decision, probable fault, severity, timestamp, and `Investigate`.

## 4. Station Investigation

### Purpose

Answer:

> Why does AtmoTrust trust or distrust this observation?

### Required layout

1. Station selector/header and T/P/RH variable tabs.
2. Variable summary cards.
3. Observed-versus-expected main chart.
4. Trust panel and evidence cards.
5. Peer comparison.
6. Operator actions.

Display separately:

- latest value and unit;
- Trust Score or `N/A`;
- label and decision;
- confidence;
- severity;
- probable fault type;
- source/provider and timestamp.

The main chart shows observed values, expected values when available, and peer median or nearby peers. When simulation is active, raw/source and test-overlay values may be compared, but raw values must not be presented as model input.

Show the strongest two to four backend evidence items. Each card contains a short label and one measured fact.

Operator actions:

- Acknowledge;
- Confirm Genuine;
- Confirm Fault.

These actions record human review; they do not overwrite the model assessment.

## 5. Maintenance Centre

### Purpose

Answer:

> What should the operator inspect first?

### Required layout

1. Ranked issue table.
2. Selected incident details.
3. Sensor Health trend and recommendation.
4. Operator-action history.

Table columns:

- priority;
- station and variable;
- probable fault;
- severity;
- Sensor Health;
- incident duration;
- status.

`Maintenance Complete` records an action and resolves the current workflow item. It must not manufacture a healthy sensor reading; later observations determine recovery.

## 6. Simulation Lab

### Purpose

Give judges safe control of the real evidence pipeline.

### Run controls

- Play and Pause;
- Reset;
- 1×, 10×, and 60×;
- Replay/Live source selector;
- current sequence and source timestamp.

### Multi-fault builder

Each pending fault row/card contains:

- station;
- variable;
- Spike, Freeze, Drift, Bias/Unrealistic, Noise, or Missing;
- magnitude where relevant;
- duration in samples;
- remove action.

Allow 1–8 pending faults and one `Inject All` action. The backend validates the complete batch before scheduling it.

### Active injections

Show station, variable, fault type, scheduled/active/completed state, remaining samples, and cancellation when allowed.

### Regional event

Provide one clear `Start Regional Weather Change` control with duration and a short explanation. Keep it visually separate from sensor faults. It must be possible to run a regional event and one or more independent faults together.

Regional events are replay-only. A live sensor test must say:

> Test overlay on a preserved copy. Upstream live data is unchanged.

## 7. Required states

### Backend starting

Show a neutral loading/retry panel. Do not show a healthy network before the first snapshot.

### WebSocket disconnected

Keep the last state visibly marked stale, reconnect with backoff, and fetch a fresh snapshot.

### Live unavailable

Show provider, last successful fetch if any, error summary, and a clear Replay option.

### Model unavailable

Show raw readings with `Analysis unavailable`. Never substitute fixed scores.

### Insufficient context

Show Trust Score `N/A` and the reason, such as waiting for history or too few usable peers.

### Missing observation

Show a chart gap, `Missing data`, and its incident.

### Empty maintenance queue

Show a calm “No open maintenance issues” state, not a blank table.

## 8. Synchronization rules

- One backend frame updates map, charts, station cards, alerts, and maintenance together.
- A pending fault appears in the Lab immediately, but analytical effects appear only after a processed backend frame.
- Operator actions appear everywhere they are relevant.
- Reset replaces old-generation UI with the reset snapshot.
- Clients ignore old generations and duplicate state versions.
- Every page reads the same shared frontend store.

## 9. Golden five-minute demo

1. **Healthy network:** start with warmed history, moving charts, and mostly genuine states.
2. **Judge injection:** choose one station, Temperature, Spike, clear magnitude, and 1–3 samples.
3. **Synchronized reaction:** show marker, alert, score, and maintenance change in the second window.
4. **Explain:** open Investigation and show temporal jump, peer disagreement, residual, confidence, severity, and fault type.
5. **Act:** acknowledge the incident in Maintenance.
6. **Reset:** prove both clients return to the same clean generation.
7. **Genuine event:** start the regional scenario and show coherent movement without a network-wide false alarm.
8. **Compound case:** add Freeze or Drift to one station and show it is isolated.
9. **Live proof:** switch briefly to the genuine provider and show source time, or show the honest degraded state and continue.

The demo must work twice in succession without editing code or restarting individual modules.

## 10. Recovery behaviour

- Use a fixed demo window and seed.
- Keep a tested local production build.
- If the hosted backend fails, use the documented local start command.
- If tiles fail, use the geographic fallback.
- If live data fails, remain fully functional in Replay mode.
- If an optional chart/model feature fails, preserve the core data and explanation path.
- Never leave the audience watching an indefinite spinner.

## 11. Accessibility and usability

- Keyboard-focusable controls.
- Visible focus states and accessible labels.
- Text contrast suitable for dashboard viewing.
- Status text in addition to colour.
- Confirmation for Reset and Maintenance Complete.
- Disabled controls explain why they are unavailable.
- Errors appear near the triggering control and do not wipe current state.

## 12. Frontend acceptance checklist

- [ ] The four pages render from one shared backend state.
- [ ] Auto-created/reused demo run begins without manual setup.
- [ ] Map/fallback and station selection work.
- [ ] T/P/RH charts move from backend points.
- [ ] Missing values produce gaps.
- [ ] Trust, confidence, severity, and health are clearly distinct.
- [ ] Evidence matches the backend assessment.
- [ ] Multi-fault batch and compound regional scenario work.
- [ ] Maintenance ranking and actions come from the backend.
- [ ] Loading, stale, disconnected, degraded, error, and empty states exist.
- [ ] No fake frontend timer, score, alert, or station state exists.
- [ ] Production build works at both target desktop resolutions.
- [ ] Two-client golden flow passes twice after reset.
