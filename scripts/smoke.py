"""Production static/API and two-client golden-flow smoke test, twice after reset."""
import sys
import secrets
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
_test_database_dir = tempfile.TemporaryDirectory(prefix="atmotrust-smoke-")
os.environ["ATMOTRUST_DATABASE_PATH"] = str(Path(_test_database_dir.name) / "operations.sqlite3")
from app.main import app, controller


def main():
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200 and "AtmoTrust" in page.text
        username, password = f"smoke_{secrets.token_hex(6)}", secrets.token_urlsafe(20)
        controller.ops.create_user(username, "Smoke Authority", "authority", password)
        assert client.post("/api/v1/auth/login", json={"username": username, "password": password, "role": "authority"}).status_code == 200
        state = client.post("/api/v1/runs").json()
        rid = state["run_id"]
        client.post(f"/api/v1/runs/{rid}/commands", json={"command": "pause"})
        with client.websocket_connect(f"/api/v1/runs/{rid}/ws?contract_version=2.0.0") as one, client.websocket_connect(f"/api/v1/runs/{rid}/ws?contract_version=2.0.0") as two:
            assert one.receive_json()["type"] == two.receive_json()["type"] == "snapshot"
            def request(path, body):
                response = client.post(f"/api/v1/runs/{rid}{path}", json=body)
                assert response.status_code == 200, response.text
                expected = response.json()["state_version"]
                left, right = one.receive_json(), two.receive_json()
                assert left["state_version"] == right["state_version"]
                while left["state_version"] < expected:
                    left, right = one.receive_json(), two.receive_json()
                    assert left["state_version"] == right["state_version"]
                assert left["state_version"] == expected
                assert left["generation"] == right["generation"]
                return response.json()
            for cycle in range(2):
                reset = request("/commands", {"command": "reset"})
                assert not reset["active_incidents"]
                request("/injections/batch", {"injections": [{"station_id": "CHD-01", "variable": "temperature_c", "fault_type": "spike", "magnitude": 9, "duration_samples": 3}]})
                spiked = request("/commands", {"command": "step"})
                target = next(a for a in spiked["latest_assessments"] if a["station_id"] == "CHD-01" and a["variable"] == "temperature_c")
                assert target["decision"] == "likely_fault" and target["evidence"] and spiked["maintenance_items"]
                incident = spiked["maintenance_items"][0]
                acted = request(f"/incidents/{incident['incident_id']}/actions", {"action": "acknowledge"})
                assert acted["operator_actions"][-1]["action"] == "acknowledge"
                if cycle == 0:
                    request("/commands", {"command": "reset"})
                    batch = request("/injections/batch", {"injections": [
                        {"station_id": "CHD-01", "variable": "temperature_c", "fault_type": "spike", "magnitude": 12, "duration_samples": 1},
                        {"station_id": "MOH-01", "variable": "humidity_pct", "fault_type": "missing", "magnitude": 0, "duration_samples": 2},
                    ]})
                    assert len({i["start_sequence"] for i in batch["active_injections"]}) == 1
                    both = request("/commands", {"command": "step"})
                    changed = [o for o in both["recent_observations"] if o["sequence"] == both["sequence"] and o["is_test_overlay"]]
                    assert len(changed) == 2 and any(o["value"] is None for o in changed)
                    assert any(o["value"] is not None and o["value"] != o["raw_value"] for o in changed)
                    active = next(i for i in both["active_injections"] if i["status"] == "active")
                    cancellation = client.delete(f"/api/v1/runs/{rid}/injections/{active['injection_id']}")
                    assert cancellation.status_code == 200
                    assert one.receive_json()["state_version"] == two.receive_json()["state_version"] == cancellation.json()["state_version"]
                    recovered = request("/commands", {"command": "step"})
                    assert next(o for o in recovered["recent_observations"] if o["sequence"] == recovered["sequence"] and o["station_id"] == "MOH-01" and o["variable"] == "humidity_pct")["value"] is not None
                    for fault in ("freeze", "drift", "bias", "noise", "missing"):
                        request("/commands", {"command": "reset"})
                        request("/injections/batch", {"injections": [{"station_id": "CHD-01", "variable": "temperature_c", "fault_type": fault, "magnitude": 12, "duration_samples": 4}]})
                        for slot in range(4):
                            frame = request("/commands", {"command": "step"})
                            observation = next(o for o in frame["recent_observations"] if o["sequence"] == frame["sequence"] and o["station_id"] == "CHD-01" and o["variable"] == "temperature_c")
                            assert observation["is_test_overlay"] and (observation["value"] is None if fault == "missing" else observation["raw_value"] is not None)
                            assert any(a["sample_id"] == observation["sample_id"] for a in frame["latest_assessments"])
                        recovered = request("/commands", {"command": "step"})
                        observation = next(o for o in recovered["recent_observations"] if o["sequence"] == recovered["sequence"] and o["station_id"] == "CHD-01" and o["variable"] == "temperature_c")
                        assert observation["value"] == observation["raw_value"] and not observation["is_test_overlay"]
                request("/commands", {"command": "reset"})
                request("/regional-events", {"duration_samples": 12})
                regional = request("/commands", {"command": "step"})
                assert sum(a["decision"] == "likely_fault" for a in regional["latest_assessments"]) <= 2
                request("/injections/batch", {"injections": [{"station_id": "CHD-01", "variable": "temperature_c", "fault_type": "spike", "magnitude": 9, "duration_samples": 3}]})
                compound = request("/commands", {"command": "step"})
                faults = [a for a in compound["latest_assessments"] if a["decision"] == "likely_fault"]
                assert any(a["station_id"] == "CHD-01" and a["variable"] == "temperature_c" for a in faults)
                print(f"golden cycle {cycle + 1}: generation {compound['generation']}, spike and compound passed, {len(faults)} fault assessments")
            request("/commands", {"command": "set_source", "source_mode": "live"})
            live = request("/commands", {"command": "step"})
            status = next(s for s in live["source_status"] if s["source_mode"] == "live")
            assert status["status"] in ("available", "unavailable")
            if status["status"] == "unavailable":
                assert live["status"] == "degraded" and "Provider unavailable" in status["detail"]
            else:
                assert status["source_timestamp"] and status["fetched_at"]
            print(f"live lane: {status['status']}")
    print("static page, REST, two WebSockets, actions, reset, regional, compound, and live lane passed")


if __name__ == "__main__":
    try:
        main()
    finally:
        controller.db.close()
        _test_database_dir.cleanup()
