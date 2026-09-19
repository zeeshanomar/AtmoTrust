# Chronological injected-fault benchmark

Source: `open_meteo_archive_gridded` (gridded_reanalysis). 9 episodes, 108 frames, 1620 observations, 32 injected fault slots.

| Method | Precision | Recall | F1 | False alarm rate |
|---|---:|---:|---:|---:|
| physical_only | 0.875 | 0.438 | 0.583 | 0.001 |
| isolation_forest_only | 0.411 | 0.719 | 0.523 | 0.021 |
| full | 0.879 | 0.906 | 0.892 | 0.003 |

Per-fault precision/recall/F1: {'clean': {'precision': 0.9993, 'recall': 0.954, 'f1': 0.9762}, 'spike': {'precision': 0.3333, 'recall': 1.0, 'f1': 0.5}, 'freeze': {'precision': 1.0, 'recall': 0.8333, 'f1': 0.9091}, 'drift': {'precision': 0.2308, 'recall': 1.0, 'f1': 0.375}, 'bias': {'precision': 0.5556, 'recall': 0.8333, 'f1': 0.6667}, 'noise': {'precision': 0.4, 'recall': 0.6667, 'f1': 0.5}, 'missing': {'precision': 1.0, 'recall': 1.0, 'f1': 1.0}, 'unknown': {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}}. Type macro-F1: 0.704. Mean/p95 frame analysis latency: 72.39/93.24 ms. Model size: 5057266 bytes.

Injected episodes on later chronological frames not used for training; repeated clean context across episodes. Labels are simulated, not observed physical sensor failures. Shared geography and earlier rule tuning limit external validity.
