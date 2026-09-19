"""Keep integration tests away from the active local demo database."""

import os
import tempfile
from pathlib import Path


_test_database_dir = tempfile.TemporaryDirectory(prefix="atmotrust-tests-")
os.environ["ATMOTRUST_DATABASE_PATH"] = str(Path(_test_database_dir.name) / "operations.sqlite3")


def pytest_sessionfinish(session, exitstatus):
    from app.main import controller

    controller.db.close()
    _test_database_dir.cleanup()
