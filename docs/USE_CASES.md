# Operational use cases

All cases run in **Simulation Lab** on the prepared replay. Replay starts automatically at 1×. Select a station and variable, add a fault, choose magnitude and duration, then **Inject All**; the next automatic frame applies it. While paused, use **Next frame** or **Play**. Open **Investigation** for measured evidence and **Maintenance** for workflow.

| Case | Suggested setup | Expected visible path |
|---|---|---|
| Spike | Chandigarh temperature, +9 °C, 1 sample | Isolated excursion, peer disagreement, low trust, incident; next sample recovers to source. |
| Freeze | Chandigarh temperature, 0 magnitude, 8 samples | Repeated value as peers change; trust declines with persistence. |
| Drift | Chandigarh temperature, +12 °C total, 8 samples | Growing residual and peer divergence; maintenance calibration advice. |
| Bias / unrealistic | Chandigarh humidity, +35%, 6 samples | Persistent offset or invalid physical range. |
| Noise | Chandigarh temperature, magnitude 9 °C, 8 samples | Deterministic high-frequency variation and unstable history. |
| Missing / data loss | Chandigarh temperature, 0 magnitude, 3 samples | Chart gap, `N/A` score, missing-data incident and communications advice. |
| Regional weather | Start the 12-sample regional change alone | Coherent T/P/RH movement across five locations; mostly genuine decisions. |
| Compound | Start regional change, then inject one Chandigarh temperature spike | Coherent peers remain trustworthy while the isolated sensor produces an incident. |

Batch two different station-variable faults in one **Inject All** request to show the same start sequence. **Reset** clears run-derived state and increments generation in every browser window. Actions record review or resolution without changing the model's assessment.

The current prepared replay is Open-Meteo Archive gridded data. A successful live fetch is Open-Meteo gridded current weather. Live faults alter preserved test copies only, with RAW LIVE and TEST COPY shown separately. If the provider is unavailable, no live values or overlays are fabricated. Neither source is physical station telemetry. The preparation script can generate a clearly labelled synthetic fallback if Archive retrieval is unavailable.
