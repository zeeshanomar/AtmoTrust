import secrets
import sqlite3
import sys
import asyncio
import importlib
from collections import deque
from pathlib import Path

from fastapi.testclient import TestClient

from app.analysis import TrustEngine
from app.controller import RunController
from app.data import PreparedSource
from app.main import app, controller
from app.operations import Operations, hash_password, verify_password
from app.schema import Assessment, Incident, InjectionSpec

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def account(role):
    username, password = f"{role}_{secrets.token_hex(6)}", secrets.token_urlsafe(20)
    user = controller.ops.create_user(username, role.title(), role, password)
    return user, username, password


def login(client, username, password, role):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password, "role": role})


class BrowserSession:
    """Two independent cookie jars on one TestClient lifespan and event loop."""
    def __init__(self, client):
        self.client = client
        self.cookie = ""

    def _call(self, method, path, **kwargs):
        response = self.client.request(method, path, headers={"cookie": self.cookie}, **kwargs)
        if path == "/api/v1/auth/login" and response.status_code == 200:
            self.cookie = response.headers["set-cookie"].split(";", 1)[0]
            self.client.cookies.clear()
        return response

    def get(self, path, **kwargs):
        return self._call("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._call("POST", path, **kwargs)

    def patch(self, path, **kwargs):
        return self._call("PATCH", path, **kwargs)

    def websocket_connect(self, path):
        return self.client.websocket_connect(path, headers={"cookie": self.cookie})


def test_password_hash_login_logout_and_landing():
    password = secrets.token_urlsafe(20)
    hashed = hash_password(password)
    assert password not in hashed and verify_password(password, hashed)
    assert not verify_password(password + "x", hashed)
    _, username, password = account("authority")
    with TestClient(app) as client:
        expected_page = 200 if (Path(__file__).resolve().parents[2] / "frontend/dist/index.html").is_file() else 404
        assert client.get("/").status_code == expected_page
        assert client.get("/login").status_code == expected_page
        assert client.get("/authority").status_code == expected_page
        assert client.post("/api/v1/runs").status_code == 401
        assert login(client, username, "wrong", "authority").status_code == 401
        assert login(client, username, password, "employee").status_code == 401
        result = login(client, username, password, "authority")
        assert result.status_code == 200 and "httponly" in result.headers["set-cookie"].lower()
        assert client.post("/api/v1/runs").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.post("/api/v1/runs").status_code == 401


def test_roles_assignments_tasks_and_websocket():
    _, authority_name, authority_password = account("authority")
    employee, employee_name, employee_password = account("employee")
    controller.ops.assign(employee["id"], "CHD-01")
    with TestClient(app) as client:
        admin, worker = BrowserSession(client), BrowserSession(client)
        assert login(admin, authority_name, authority_password, "authority").status_code == 200
        assert login(worker, employee_name, employee_password, "employee").status_code == 200
        rid = admin.post("/api/v1/runs").json()["run_id"]
        admin.post(f"/api/v1/runs/{rid}/commands", json={"command": "pause"})
        admin.post(f"/api/v1/runs/{rid}/commands", json={"command": "reset"})
        assert admin.post(f"/api/v1/runs/{rid}/injections/batch", json={"injections": [
            {"station_id": "CHD-01", "variable": "temperature_c", "fault_type": "spike", "magnitude": 12, "duration_samples": 1},
            {"station_id": "MOH-01", "variable": "temperature_c", "fault_type": "spike", "magnitude": 12, "duration_samples": 1},
        ]}).status_code == 200
        state = admin.post(f"/api/v1/runs/{rid}/commands", json={"command": "step"}).json()
        assert {i["station_id"] for i in state["maintenance_items"]} >= {"CHD-01", "MOH-01"}
        own_incident = next(i["incident_id"] for i in state["maintenance_items"] if i["station_id"] == "CHD-01")
        assert admin.patch(f"/api/v1/admin/tasks/{own_incident}/assignee", json={"user_id": employee["id"]}).status_code == 200
        employee_state = worker.get(f"/api/v1/runs/{rid}/state").json()
        assert {s["station_id"] for s in employee_state["stations"]} == {"CHD-01"}
        assert all("maintenance_email" not in station for station in employee_state["stations"])
        assert {o["station_id"] for o in employee_state["recent_observations"]} == {"CHD-01"}
        tasks = worker.get("/api/v1/tasks").json()
        assert tasks and {t["station_id"] for t in tasks} == {"CHD-01"}
        own = tasks[0]["incident_id"]
        other = next(i["incident_id"] for i in state["maintenance_items"] if i["station_id"] == "MOH-01")
        for path, payload in ((f"/runs/{rid}/commands", {"command": "reset"}), (f"/runs/{rid}/injections/batch", {"injections": []}), (f"/runs/{rid}/regional-events", {"duration_samples": 12}), (f"/runs/{rid}/incidents/{own}/actions", {"action": "confirm_fault"}), ("/admin/employees", {"username": "x", "display_name": "x", "password": secrets.token_urlsafe(20)})):
            assert worker.post("/api/v1" + path, json=payload).status_code == 403
        assert worker.get("/api/v1/admin/users").status_code == 403
        assert worker.get(f"/api/v1/tasks/{other}/notes").status_code == 403
        assert worker.patch(f"/api/v1/tasks/{other}", json={"status": "Maintenance In Progress"}).status_code == 403
        with admin.websocket_connect(f"/api/v1/runs/{rid}/ws?contract_version=2.0.0") as authority_ws, worker.websocket_connect(f"/api/v1/runs/{rid}/ws?contract_version=2.0.0") as employee_ws:
            assert authority_ws.receive_json()["type"] == employee_ws.receive_json()["type"] == "snapshot"
            started = worker.patch(f"/api/v1/tasks/{own}", json={"status": "Maintenance In Progress"})
            assert started.status_code == 200
            authority_update, employee_update = authority_ws.receive_json(), employee_ws.receive_json()
            assert authority_update["state_version"] == employee_update["state_version"]
            assert next(i for i in authority_update["state"]["active_incidents"] if i["incident_id"] == own)["task_status"] == "Maintenance In Progress"
            notifications = admin.get("/api/v1/authority/notifications").json()
            assert notifications["unread_count"] == 1 and notifications["items"][0]["event_type"] == "maintenance_started"
            assert worker.get("/api/v1/authority/notifications").status_code == 403
            assert worker.post(f"/api/v1/tasks/{own}/notes", json={"body": "Checked power supply"}).status_code == 200
            assert authority_ws.receive_json()["state_version"] == employee_ws.receive_json()["state_version"]
            notifications = admin.get("/api/v1/authority/notifications").json()
            assert notifications["unread_count"] == 2 and notifications["items"][0]["event_type"] == "maintenance_note"
            assert "Checked power supply" in notifications["items"][0]["body"]
            completed = worker.patch(f"/api/v1/tasks/{own}", json={"status": "Maintained"})
            assert completed.status_code == 200
            assert authority_ws.receive_json()["state"]["active_incidents"]
            assert employee_ws.receive_json()["state"]["active_incidents"]
            notifications = admin.get("/api/v1/authority/notifications").json()
            assert notifications["unread_count"] == 3 and notifications["items"][0]["event_type"] == "maintenance_completed"
            assert worker.patch(f"/api/v1/authority/notifications/{notifications['items'][0]['id']}/read").status_code == 403
            assert admin.patch(f"/api/v1/authority/notifications/{notifications['items'][0]['id']}/read").status_code == 200
            authority_ws.receive_json(); employee_ws.receive_json()
            assert admin.get("/api/v1/authority/notifications").json()["unread_count"] == 2
            assert admin.post("/api/v1/authority/notifications/read-all").json()["unread_count"] == 0
            authority_ws.receive_json(); employee_ws.receive_json()
            assert worker.get(f"/api/v1/tasks/{own}/notes").json()[0]["body"] == "Checked power supply"
            assert worker.get("/api/v1/tasks").json()[0]["status"] == "Maintained"
            with sqlite3.connect(controller.db_path) as persisted:
                assert persisted.execute("SELECT COUNT(*) FROM authority_notifications WHERE incident_id=?", (own,)).fetchone()[0] == 3
                assert persisted.execute("SELECT COUNT(*) FROM maintenance_notes WHERE incident_id=?", (own,)).fetchone()[0] == 1


def test_single_lifespan_owns_replay_clock():
    controller.status = "running"
    with TestClient(app) as client:
        assert controller.clock is not None
        assert controller.clock.get_loop() is client.portal.call(asyncio.get_running_loop)
        controller.status = "paused"
    assert controller.clock is None


def test_history_frame_width_tracks_configured_stations(tmp_path, monkeypatch):
    module = importlib.import_module("app.main")
    local = RunController(database_path=tmp_path / "history.sqlite3")
    local.status = "paused"
    local.source.stations = local.source.stations[:2]
    station_ids = {station["station_id"] for station in local.source.stations}
    local.chart = deque((item for sequence in (50, 51, 52) for item in local.source.read_frame(sequence) if item.station_id in station_ids), maxlen=900)
    monkeypatch.setattr(module, "controller", local)
    password = secrets.token_urlsafe(20)
    user = local.ops.create_user("history_authority", "History Authority", "authority", password)
    with TestClient(app) as client:
        assert login(client, user["username"], password, "authority").status_code == 200
        rows = client.get(f"/api/v1/runs/{local.run_id}/history?limit=2").json()["observations"]
        assert len(rows) == 2 * len(local.source.stations) * 3
        assert {item["sequence"] for item in rows} == {51, 52}


def test_combined_employee_status_and_note_creates_one_notification(tmp_path):
    db = sqlite3.connect(tmp_path / "combined.sqlite3")
    ops = Operations(db, PreparedSource().stations)
    employee = ops.create_user("combined_employee", "Field Engineer", "employee", secrets.token_urlsafe(20))
    station = ops.stations()[0]
    ops.assign(employee["id"], station["station_id"])
    incident = Incident(incident_id=secrets.token_hex(12), station_id=station["station_id"], variable="temperature_c", opened_at="2026-08-01T00:00:00Z", last_seen_at="2026-08-01T00:00:00Z", fault_type="spike", severity="high", confidence=.8)
    assessment = Assessment(sample_id="combined", station_id=station["station_id"], variable="temperature_c", timestamp=incident.opened_at, assessment_status="complete", trust_score=20, confidence=.8)
    ops.record_incident(incident, assessment, "combined-run", 1)
    result = ops.update_task(incident.incident_id, employee, "Maintenance In Progress", "Connector reseated")
    notices = ops.authority_notifications()
    assert result["status"] == "Maintenance In Progress"
    assert notices["unread_count"] == 1 and len(notices["items"]) == 1
    assert notices["items"][0]["event_type"] == "maintenance_started"
    assert "Connector reseated" in notices["items"][0]["body"]
    assert ops.notes(incident.incident_id, employee)[0]["body"] == "Connector reseated"
    db.close()


def test_email_dedup_escalation_outbox_and_failure(tmp_path, monkeypatch):
    db = sqlite3.connect(tmp_path / "operations.sqlite3")
    ops = Operations(db, PreparedSource().stations)
    station = ops.stations()[0]
    ops.update_station(station["station_id"], station["name"], station["pole_id"], "maintainer@example.test", station["criticality"])
    incident = Incident(incident_id=secrets.token_hex(12), station_id=station["station_id"], variable="temperature_c", opened_at="2026-08-01T00:00:00Z", last_seen_at="2026-08-01T00:00:00Z", fault_type="spike", severity="high", confidence=.8)
    assessment = Assessment(sample_id="test", station_id=station["station_id"], variable="temperature_c", timestamp=incident.opened_at, assessment_status="complete", trust_score=20, confidence=.8, observed_value=40, expected_value=30, fault_type="spike", explanation="Sudden isolated jump", resolution="Inspect wiring")
    ops.record_incident(incident, assessment, "test-run", 1)
    first = ops.queue_email(incident, assessment, "opened")
    assert first["status"] == "queued" and "Sudden isolated jump" in first["body"] and station["pole_id"] in first["body"]
    assert ops.queue_email(incident, assessment, "opened") is None
    monkeypatch.delenv("ATMOTRUST_SMTP_HOST", raising=False)
    assert ops.deliver(first["id"]) == "outbox"
    assert ops.emails()[0]["status"] == "outbox"
    incident.severity = "critical"
    escalated = ops.queue_email(incident, assessment, "severity_critical")
    assert escalated and len(ops.emails()) == 2
    monkeypatch.setenv("ATMOTRUST_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("ATMOTRUST_EMAIL_ENABLED", "true")
    monkeypatch.setattr("app.operations.smtplib.SMTP", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("secret host detail")))
    assert ops.deliver(escalated["id"]) == "failed"
    assert "secret host detail" not in ops.emails()[0]["safe_error"]
    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def starttls(self): pass
        def login(self, *args): pass
        def send_message(self, message): assert "AtmoTrust" in message["Subject"]
    monkeypatch.setattr("app.operations.smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("ATMOTRUST_SMTP_SENDER", "alerts@example.test")
    manual = ops.queue_email(incident, assessment, "manual_test")
    assert ops.deliver(manual["id"]) == "sent"
    assert ops.emails()[0]["status"] == "sent"


def test_saved_model_chronology_leakage_and_unavailable(tmp_path):
    from scripts.train_model import split_bounds
    source = PreparedSource()
    splits = split_bounds(source.total_frames)
    assert splits["train"][1] == splits["validation"][0]
    assert splits["validation"][1] == splits["test"][0]
    model = TrustEngine(source.policy, source.data_dir.parents[2] / "artifacts/demo_v1/isolation_forest.joblib")
    assert model.model is not None and model.classifier is not None
    first = source.read_frame(0)[0].model_input()
    first["raw_value"] = -999
    assert "raw_value" not in model.classifier_features({"value": first["value"], "values": []}, first["variable"]).__str__()
    missing = TrustEngine(source.policy, tmp_path / "missing.joblib")
    assessments, _ = missing.analyze_frame([first], {}, source.stations)
    assert assessments[0].assessment_status == "insufficient_context"
    history = {(first["station_id"], first["variable"]): [{"value": first["value"], "residual": 0}] * 24}
    unavailable, _ = missing.analyze_frame([first], history, source.stations)
    assert unavailable[0].assessment_status == "model_unavailable" and unavailable[0].trust_score is None


def test_automatic_alert_once_for_open_incident(tmp_path, monkeypatch):
    monkeypatch.setenv("ATMOTRUST_EMAIL_ENABLED", "false")
    c = RunController(database_path=tmp_path / "auto.sqlite3")
    station = next(item for item in c.source.stations if item["station_id"] == "CHD-01")
    c.ops.update_station(station["station_id"], station["name"], station["pole_id"], "crew@example.test", station["criticality"])
    async def scenario():
        await c.inject([InjectionSpec(station_id="CHD-01", variable="temperature_c", fault_type="spike", magnitude=12, duration_samples=3)])
        await c.step()
        first = c.ops.emails()
        assert len(first) == 1 and first[0]["reason"] == "opened"
        await c.step()
        assert len(c.ops.emails()) == 1
        for _ in range(50):
            if c.ops.emails()[0]["status"] == "outbox":
                break
            await asyncio.sleep(.01)
        assert c.ops.emails()[0]["status"] == "outbox"
    asyncio.run(scenario())
