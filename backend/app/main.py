import asyncio
import os
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .controller import RunController
from .schema import Assessment, Command, Incident, InjectionSpec, UNITS, now

@asynccontextmanager
async def lifespan(_app):
    loop = asyncio.get_running_loop()
    controller.pending_emails.extend(row["id"] for row in controller.ops.emails() if row["status"] == "queued")
    controller.schedule_emails()
    if controller.status == "running" and (controller.clock is None or controller.clock.done()):
        controller.clock = asyncio.create_task(controller.run_clock())
    try:
        yield
    finally:
        clock = controller.clock
        if clock and clock.get_loop() is loop:
            if not clock.done():
                clock.cancel()
            try:
                await clock
            except asyncio.CancelledError:
                pass
            if controller.clock is clock:
                controller.clock = None
        email_tasks = [task for task in controller.email_tasks if task.get_loop() is loop]
        if email_tasks:
            await asyncio.gather(*email_tasks, return_exceptions=True)


app = FastAPI(title="AtmoTrust", version="1.0.0", lifespan=lifespan)
origins = [item.strip() for item in os.getenv("ATMOTRUST_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["*"], allow_credentials=True)
controller = RunController()


class InjectionBatch(BaseModel):
    injections: list[InjectionSpec] = Field(min_length=1, max_length=8)


class RegionalRequest(BaseModel):
    duration_samples: int = Field(default=12, ge=4, le=48)


class ActionRequest(BaseModel):
    action: str


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str


class UserRequest(BaseModel):
    username: str
    display_name: str
    password: str = Field(min_length=12)


class AssignmentRequest(BaseModel):
    user_id: str
    station_id: str
    assigned: bool = True


class StationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    pole_id: str = Field(min_length=1, max_length=80)
    maintenance_email: str | None = None
    criticality: float = Field(ge=0, le=1)


class TaskRequest(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=2000)


class TaskAssigneeRequest(BaseModel):
    user_id: str


class NoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


def current_user(request: Request):
    user = controller.ops.session(request.cookies.get("atmotrust_session"))
    if not user:
        raise HTTPException(401, "Login required")
    return user


def authority(user=Depends(current_user)):
    if user["role"] != "authority":
        raise HTTPException(403, "Authority access required")
    return user


@app.post("/api/v1/auth/login")
def login(body: LoginRequest, response: Response):
    result = controller.ops.login(body.username, body.password)
    if not result or result[1]["role"] != body.role:
        if result:
            controller.ops.logout(result[0])
        raise HTTPException(401, "Invalid credentials")
    token, user = result
    response.set_cookie("atmotrust_session", token, httponly=True, secure=os.getenv("ATMOTRUST_COOKIE_SECURE", "false").lower() == "true", samesite="strict", max_age=43200, path="/")
    return user


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response):
    controller.ops.logout(request.cookies.get("atmotrust_session"))
    response.delete_cookie("atmotrust_session", path="/")
    return {"ok": True}


@app.get("/api/v1/auth/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/v1/health")
def health():
    return {"ready": True, "build": "local", "contract_version": "2.0.0", "timestamp": now()}


@app.get("/api/v1/catalog")
def catalog(user=Depends(current_user)):
    stations = controller.source.stations if user["role"] == "authority" else [{k: v for k, v in s.items() if k != "maintenance_email"} for s in controller.source.stations if s["station_id"] in {a["station_id"] for a in controller.ops.assignments(user["id"])}]
    return {"stations": stations, "sources": [controller.source.status().model_dump(), controller.live_status.model_dump()], "variables": ["temperature_c", "pressure_hpa", "humidity_pct"], "scenarios": ["coherent_weather_change"] if user["role"] == "authority" else [], "fault_types": ["spike", "freeze", "drift", "bias", "noise", "missing"]}


@app.post("/api/v1/runs")
def create_run(user=Depends(current_user)):
    return controller.snapshot(controller.run_id, user)


@app.get("/api/v1/runs/{run_id}/state")
def state(run_id: str, user=Depends(current_user)):
    return controller.snapshot(run_id, user)


@app.get("/api/v1/runs/{run_id}/history")
def history(run_id: str, limit: int = 60, user=Depends(current_user)):
    controller.snapshot(run_id)
    if not 1 <= limit <= 60:
        raise HTTPException(422, "limit must be 1 to 60 frames")
    allowed = None if user["role"] == "authority" else {a["station_id"] for a in controller.ops.assignments(user["id"])}
    rows = [o for o in controller.chart if allowed is None or o.station_id in allowed]
    station_ids = {station["station_id"] for station in controller.source.stations}
    visible_stations = len(station_ids if allowed is None else station_ids & allowed)
    frame_width = visible_stations * len(UNITS)
    return {"run_id": run_id, "generation": controller.generation, "observations": rows[-limit * frame_width:] if frame_width else []}


@app.post("/api/v1/runs/{run_id}/commands")
async def command(run_id: str, body: Command, _user=Depends(authority)):
    controller.snapshot(run_id)
    return await controller.command(body)


@app.post("/api/v1/runs/{run_id}/injections/batch")
async def inject(run_id: str, body: InjectionBatch, _user=Depends(authority)):
    controller.snapshot(run_id)
    return await controller.inject(body.injections)


@app.delete("/api/v1/runs/{run_id}/injections/{injection_id}")
async def cancel(run_id: str, injection_id: str, _user=Depends(authority)):
    controller.snapshot(run_id)
    return await controller.cancel(injection_id)


@app.post("/api/v1/runs/{run_id}/regional-events")
async def regional(run_id: str, body: RegionalRequest, _user=Depends(authority)):
    controller.snapshot(run_id)
    return await controller.regional(body.duration_samples)


@app.post("/api/v1/runs/{run_id}/incidents/{incident_id}/actions")
async def action(run_id: str, incident_id: str, body: ActionRequest, _user=Depends(authority)):
    controller.snapshot(run_id)
    return await controller.act(incident_id, body.action)


@app.websocket("/api/v1/runs/{run_id}/ws")
async def websocket(websocket: WebSocket, run_id: str, contract_version: str = ""):
    user = controller.ops.session(websocket.cookies.get("atmotrust_session"))
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    permitted_origins = set(origins) | {f"http://{host}", f"https://{host}"}
    if not user or (origin and origin not in permitted_origins) or run_id != controller.run_id or contract_version != "2.0.0":
        await websocket.close(code=1008)
        return
    await websocket.accept()
    controller.clients[websocket] = websocket.cookies["atmotrust_session"]
    try:
        snapshot = controller.snapshot(run_id, user)
        await websocket.send_json({"type": "snapshot", "run_id": run_id, "generation": snapshot.generation, "state_version": snapshot.state_version, "sent_at": now(), "state": snapshot.model_dump(mode="json")})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        controller.clients.pop(websocket, None)


@app.get("/api/v1/tasks")
def tasks(user=Depends(current_user)):
    return controller.ops.tasks(user)


@app.get("/api/v1/authority/notifications")
def authority_notifications(_user=Depends(authority)):
    return controller.ops.authority_notifications()


@app.patch("/api/v1/authority/notifications/{notification_id}/read")
async def read_authority_notification(notification_id: str, _user=Depends(authority)):
    result = controller.ops.read_authority_notification(notification_id)
    if result is None:
        raise HTTPException(404, "Unknown notification")
    controller.state_version += 1
    await controller.publish()
    return result


@app.post("/api/v1/authority/notifications/read-all")
async def read_all_authority_notifications(_user=Depends(authority)):
    result = controller.ops.read_all_authority_notifications()
    controller.state_version += 1
    await controller.publish()
    return result


@app.get("/api/v1/tasks/{incident_id}/notes")
def notes(incident_id: str, user=Depends(current_user)):
    result = controller.ops.notes(incident_id, user)
    if result is None:
        raise HTTPException(403, "Task not assigned")
    return result


@app.post("/api/v1/tasks/{incident_id}/notes")
async def add_note(incident_id: str, body: NoteRequest, user=Depends(current_user)):
    result = controller.ops.add_note(incident_id, user, body.body)
    if result is None:
        raise HTTPException(403, "Task not assigned")
    controller.state_version += 1
    await controller.publish()
    return result


@app.patch("/api/v1/tasks/{incident_id}")
async def update_task(incident_id: str, body: TaskRequest, user=Depends(current_user)):
    try:
        result = controller.ops.update_task(incident_id, user, body.status, body.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if result is None:
        raise HTTPException(403, "Task not assigned")
    incident = controller.incidents.get(incident_id)
    if incident:
        incident.task_status = result["status"]
        if result["status"] == "Maintained":
            incident.status = "resolved"
        elif result["status"] in ("Reopened", "Assigned", "Maintenance In Progress"):
            incident.status = "open"
    controller.state_version += 1
    await controller.publish()
    return result


@app.patch("/api/v1/admin/tasks/{incident_id}/assignee")
async def assign_task(incident_id: str, body: TaskAssigneeRequest, _user=Depends(authority)):
    try:
        result = controller.ops.assign_task(incident_id, body.user_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    incident = controller.incidents.get(incident_id)
    if incident:
        incident.assignee_id = body.user_id
    controller.state_version += 1
    await controller.publish()
    return result


@app.get("/api/v1/admin/users")
def users(_user=Depends(authority)):
    return controller.ops.users()


@app.post("/api/v1/admin/employees")
def create_employee(body: UserRequest, _user=Depends(authority)):
    try:
        return controller.ops.create_user(body.username, body.display_name, "employee", body.password)
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(422, "Invalid or duplicate employee") from exc


@app.patch("/api/v1/admin/employees/{user_id}")
def update_employee(user_id: str, active: bool, _user=Depends(authority)):
    result = controller.ops.set_active(user_id, active)
    if not result:
        raise HTTPException(404, "Unknown employee")
    return result


@app.get("/api/v1/admin/assignments")
def assignments(_user=Depends(authority)):
    return controller.ops.assignments()


@app.post("/api/v1/admin/assignments")
async def assign(body: AssignmentRequest, _user=Depends(authority)):
    try:
        controller.ops.assign(body.user_id, body.station_id, body.assigned)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    controller.state_version += 1
    await controller.publish()
    return controller.ops.assignments()


@app.put("/api/v1/admin/stations/{station_id}")
async def update_station(station_id: str, body: StationRequest, _user=Depends(authority)):
    try:
        result = controller.ops.update_station(station_id, body.name, body.pole_id, body.maintenance_email, body.criticality)
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(422, "Invalid station data") from exc
    controller.source.stations = controller.ops.stations()
    controller.live.stations = controller.source.stations
    controller.state_version += 1
    await controller.publish()
    return result


@app.get("/api/v1/admin/emails")
def emails(_user=Depends(authority)):
    return controller.ops.emails()


@app.post("/api/v1/admin/emails/{incident_id}/resend")
def resend(incident_id: str, _user=Depends(authority)):
    row = controller.db.execute("SELECT * FROM operational_incidents WHERE incident_id=?", (incident_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown incident")
    incident = controller.incidents.get(incident_id) or Incident(incident_id=row["incident_id"], station_id=row["station_id"], variable=row["variable"], opened_at=row["opened_at"], last_seen_at=row["last_seen_at"], fault_type=row["fault_type"], severity=row["severity"], confidence=0)
    assessment = Assessment.model_validate_json(row["assessment_json"])
    import uuid
    delivery = controller.ops.queue_email(incident, assessment, f"manual_{uuid.uuid4().hex}")
    if delivery and delivery["status"] == "queued":
        controller.pending_emails.append(delivery["id"])
        controller.schedule_emails()
    return delivery


@app.get("/api/v1/admin/model")
def model_info(_user=Depends(authority)):
    path = Path(os.getenv("ATMOTRUST_ARTIFACT_DIR", str(Path(__file__).resolve().parents[2] / "artifacts/demo_v1"))) / "manifest.json"
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    if not path.exists():
        return {"status": "Analysis unavailable"}
    return {"status": "loaded" if controller.engine.model is not None and controller.engine.classifier is not None else "Analysis unavailable", **json.loads(path.read_text(encoding="utf-8"))}


DIST = Path(__file__).resolve().parents[2] / "frontend/dist"


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if not (DIST / "index.html").is_file():
        raise HTTPException(404, "Frontend build not installed")
    target = (DIST / path).resolve()
    if target.is_file() and DIST.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(DIST / "index.html")
