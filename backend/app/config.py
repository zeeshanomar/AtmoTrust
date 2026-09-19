"""Read optional local environment values without overriding process settings."""
import os
from pathlib import Path


def load_env():
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("ATMOTRUST_") and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
