import asyncio
import json
import os
import sqlite3
import uuid
from collections import defaultdict, deque
from pathlib import Path
from fastapi import HTTPException, WebSocket
from .analysis import TrustEngine
from .data import PreparedSource, LiveAdapter, ROOT
from .health import HealthEngine
from .schema import Action, Command, Incident, Injection, InjectionSpec, StatePayload, now
from .simulation import ScenarioInjector
from .operations import Operations

SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class RunController:
    def __init__(self, source=None, database_path=None):
        self.source = source or PreparedSource()
        self.live = LiveAdapter(self.source.stations)
        artifact_dir = Path(os.getenv("ATMOTRUST_ARTIFACT_DIR", str(ROOT / "artifacts/demo_v1")))
        if not artifact_dir.is_absolute():
            artifact_dir = ROOT / artifact_dir
        self.engine = TrustEngine(self.source.policy, artifact_dir / "isolation_forest.joblib")
        self.health_engine = HealthEngine()
        self.injector = ScenarioInjector()
        self.db_path = Path(database_path or os.getenv("ATMOTRUST_DATABASE_PATH", str(ROOT / "backend/atmotrust.sqlite3")))
        if not self.db_path.is_absolute():
            self.db_path = ROOT / self.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        for table, columns in {"runs": "run_id TEXT, generation INTEGER, payload TEXT", "observations": "run_id TEXT, generation INTEGER, sequence INTEGER, payload TEXT", "assessments": "run_id TEXT, generation INTEGER, sequence INTEGER, payload TEXT", "sensor_health": "run_id TEXT, generation INTEGER, sequence INTEGER, payload TEXT", "incidents": "run_id TEXT, generation INTEGER, incident_id TEXT, payload TEXT", "operator_actions": "run_id TEXT, generation INTEGER, action_id TEXT, payload TEXT", "injections": "run_id TEXT, generation INTEGER, injection_id TEXT, payload TEXT"}.items():
            self.db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({columns})")
        self.db.commit()
        self.ops = Operations(self.db, self.source.stations)
        manifest_path = artifact_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO model_metadata VALUES (?,?,?)", (manifest.get("model_version", "legacy"), json.dumps(manifest), now()))
        self.source.stations = self.ops.stations()
        self.live.stations = self.source.stations
        self.lock = asyncio.Lock()
        self.clients: dict[WebSocket, str] = {}
        self.pending_emails = []
        self.email_tasks: set[asyncio.Task] = set()
        self.clock = None
        self.run_id = str(uuid.uuid4())
        self.generation = 1
        self.state_version = 0
        self.status = "running"
        self.speed = 1
        self.source_mode = "replay"
        self.sequence = 47
        self.latest = []
        self.assessments = []
        self.health = {}
        self.history = defaultdict(lambda: deque(maxlen=60))
        self.chart = deque(maxlen=900)
        self.assessment_chart = deque(maxlen=900)
        self.incidents = {}
        self.actions = []
        self.injections = []
        self.regional_event = None
        self.live_status = self.live_unavailable("Not fetched yet")
        self.warmup()

    def live_unavailable(self, detail):
        from .schema import SourceStatus
        return SourceStatus(source_mode="live", source_name="open_meteo_current_gridded", provenance_type="current_gridded_location", status="unavailable", detail=detail)

    def warmup(self):
        start = max(0, self.sequence - 47)
        for index in range(start, self.sequence + 1):
            observations = self.source.read_frame(index, self.run_id, self.generation)
            self.process_frame(observations, persist=False)
        self.state_version = 1

    def snapshot(self, run_id, user=None):
        if run_id != self.run_id:
            raise HTTPException(404, "Unknown run")
        assessment = {(a.station_id, a.variable): a for a in self.assessments}
        stations = []
        for station in self.source.stations:
            scores = [assessment[(station["station_id"], variable)] for variable in ("temperature_c", "pressure_hpa", "humidity_pct") if (station["station_id"], variable) in assessment]
            status = "unknown"
            if any(a.decision == "likely_fault" or a.assessment_status in ("missing", "invalid") for a in scores):
                status = "fault"
            elif any(a.decision == "needs_review" for a in scores):
                status = "review"
            elif scores:
                status = "genuine"
            stations.append({**station, "status": status})
        active = self.injections[-24:]
        maintenance = sorted([i for i in self.incidents.values() if i.status in ("open", "acknowledged", "confirmed_fault")], key=lambda i: i.maintenance_priority, reverse=True)
        if user and user["role"] == "employee":
            permitted = {row["station_id"] for row in self.ops.assignments(user["id"])}
            stations = [{k: v for k, v in s.items() if k != "maintenance_email"} for s in stations if s["station_id"] in permitted]
            maintenance_ids = {t["incident_id"] for t in self.ops.tasks(user)}
            maintenance = [i for i in maintenance if i.incident_id in maintenance_ids]
            incidents = [i for i in self.incidents.values() if i.incident_id in maintenance_ids]
            chart = [o for o in self.chart if o.station_id in permitted]
            assessments = [a for a in self.assessments if a.station_id in permitted]
            assessment_chart = [a for a in self.assessment_chart if a.station_id in permitted]
            health = [h for h in self.health.values() if h.station_id in permitted]
            active = []
            actions = []
            regional = None
        else:
            incidents = list(self.incidents.values())
            chart = list(self.chart)
            assessments = self.assessments
            assessment_chart = list(self.assessment_chart)
            health = list(self.health.values())
            actions = self.actions[-40:]
            regional = self.regional_event
        return StatePayload(run_id=self.run_id, generation=self.generation, state_version=self.state_version, status=self.status, speed=self.speed, source_mode=self.source_mode, sequence=self.sequence, source_timestamp=self.latest[0].source_timestamp if self.latest else None, stations=stations, recent_observations=chart, latest_assessments=assessments, recent_assessments=assessment_chart, sensor_health=health, active_incidents=incidents, maintenance_items=maintenance, active_injections=active, regional_event=regional, source_status=[self.source.status(), self.live_status], operator_actions=actions)

    def process_frame(self, observations, persist=True):
        previous = {key: rows[-1]["value"] for key, rows in self.history.items() if rows}
        observations = self.injector.apply(observations, self.injections, self.regional_event if observations[0].source_mode == "replay" else None, observations[0].sequence, previous)
        safe = [item.model_input() for item in observations]
        assessments, features = self.engine.analyze_frame(safe, self.history, self.source.stations)
        alert_events = []
        for assessment in assessments:
            if assessment.decision == "likely_fault" or assessment.assessment_status in ("missing", "invalid"):
                key = (assessment.station_id, assessment.variable)
                incident = next((i for i in self.incidents.values() if (i.station_id, i.variable) == key and i.status in ("open", "acknowledged", "confirmed_fault")), None)
                if incident:
                    old_severity = incident.severity
                    incident.last_seen_at = assessment.timestamp
                    incident.duration_samples += 1
                    incident.fault_type = assessment.fault_type
                    incident.severity = assessment.severity
                    incident.confidence = assessment.confidence
                    if persist and SEVERITY_ORDER.get(assessment.severity, 0) > SEVERITY_ORDER.get(old_severity, 0):
                        alert_events.append((incident, assessment, f"severity_{assessment.severity}"))
                else:
                    incident = Incident(incident_id=str(uuid.uuid4()), station_id=assessment.station_id, variable=assessment.variable, opened_at=assessment.timestamp, last_seen_at=assessment.timestamp, fault_type=assessment.fault_type, severity=assessment.severity, confidence=assessment.confidence)
                    self.incidents[incident.incident_id] = incident
                    if persist:
                        alert_events.append((incident, assessment, "opened"))
        health = self.health_engine.update(assessments, self.health, list(self.incidents.values()), criticality={s["station_id"]: s["criticality"] for s in self.source.stations})
        self.health = {(item.station_id, item.variable): item for item in health}
        for incident in self.incidents.values():
            item = self.health.get((incident.station_id, incident.variable))
            if item:
                incident.health_score = item.health_score
                incident.maintenance_priority = item.maintenance_priority
                incident.recommendation = item.recommendation
        for item in observations:
            key = (item.station_id, item.variable)
            self.history[key].append({**item.model_input(), "residual": features[key].get("residual")})
            self.chart.append(item)
        self.assessment_chart.extend(assessments)
        for injection in self.injections:
            if observations[0].sequence >= injection.end_sequence - 1:
                injection.status = "completed"
                injection.remaining_samples = 0
            elif observations[0].sequence >= injection.start_sequence:
                injection.status = "active"
                injection.remaining_samples = injection.end_sequence - observations[0].sequence - 1
        self.latest, self.assessments = observations, assessments
        self.sequence = observations[0].sequence
        if persist:
            with self.db:
                self.db.executemany("INSERT INTO observations VALUES (?,?,?,?)", [(self.run_id, self.generation, self.sequence, item.model_dump_json()) for item in observations])
                self.db.executemany("INSERT INTO assessments VALUES (?,?,?,?)", [(self.run_id, self.generation, self.sequence, item.model_dump_json()) for item in assessments])
                self.db.executemany("INSERT INTO sensor_health VALUES (?,?,?,?)", [(self.run_id, self.generation, self.sequence, item.model_dump_json()) for item in health])
                for incident in self.incidents.values():
                    self.db.execute("INSERT INTO incidents VALUES (?,?,?,?)", (self.run_id, self.generation, incident.incident_id, incident.model_dump_json()))
            for incident, assessment, reason in alert_events:
                if reason == "opened":
                    self.ops.record_incident(incident, assessment, self.run_id, self.generation)
                else:
                    self.ops.update_incident(incident, assessment)
                task = self.ops.task(incident.incident_id)
                if task:
                    incident.assignee_id = task["assignee_id"]
                    incident.task_status = task["status"]
                delivery = self.ops.queue_email(incident, assessment, reason)
                if delivery and delivery["status"] == "queued":
                    self.pending_emails.append(delivery["id"])
            self.state_version += 1

    async def publish(self, kind="update"):
        for client, token in list(self.clients.items()):
            try:
                user = self.ops.session(token)
                if user is None:
                    await client.close(code=1008)
                    self.clients.pop(client, None)
                    continue
                state = self.snapshot(self.run_id, user)
                message = {"type": kind, "run_id": self.run_id, "generation": self.generation, "state_version": self.state_version, "sent_at": now(), "state": state.model_dump(mode="json")}
                await client.send_json(message)
            except Exception:
                self.clients.pop(client, None)

    def schedule_emails(self):
        while self.pending_emails:
            delivery_id = self.pending_emails.pop(0)
            task = asyncio.create_task(asyncio.to_thread(self.ops.deliver, delivery_id))
            self.email_tasks.add(task)
            task.add_done_callback(self.email_tasks.discard)

    async def step(self):
        async with self.lock:
            if self.source_mode == "replay":
                if self.sequence + 1 >= self.source.total_frames:
                    self.status = "completed"
                    return self.snapshot(self.run_id)
                observations = self.source.read_frame(self.sequence + 1, self.run_id, self.generation)
            else:
                observations, self.live_status = await self.live.fetch_latest(self.run_id, self.generation, self.sequence + 1)
                if not observations:
                    self.status = "degraded"
                    self.state_version += 1
                    await self.publish()
                    return self.snapshot(self.run_id)
                has_test = any(i.status in ("scheduled", "active") and i.start_sequence <= observations[0].sequence < i.end_sequence for i in self.injections)
                was_test = any(item.is_test_overlay for item in self.latest)
                if self.latest and self.latest[0].source_mode == "live" and self.latest[0].source_timestamp == observations[0].source_timestamp and not has_test and not was_test:
                    self.state_version += 1
                    await self.publish()
                    return self.snapshot(self.run_id)
            self.process_frame(observations)
            self.schedule_emails()
            await self.publish()
            return self.snapshot(self.run_id)

    async def run_clock(self):
        while self.status == "running":
            if self.source_mode == "live":
                await self.step()
                if self.status == "running":
                    await asyncio.sleep(60)
            else:
                await asyncio.sleep(1 / self.speed)
                if self.status == "running":
                    await self.step()

    async def command(self, command: Command):
        if command.command == "step":
            return await self.step()
        async with self.lock:
            if command.command == "set_speed":
                if command.speed is None:
                    raise HTTPException(422, "speed is required")
                self.speed = command.speed
            elif command.command == "set_source":
                if command.source_mode is None:
                    raise HTTPException(422, "source_mode is required")
                self.source_mode = command.source_mode
                self.status = "paused"
                self.generation += 1
                self.sequence = 47
                self.history.clear(); self.chart.clear(); self.assessment_chart.clear(); self.incidents.clear(); self.actions.clear(); self.injections.clear(); self.health.clear()
                self.latest = []; self.assessments = []; self.regional_event = None
                if self.source_mode == "replay":
                    self.warmup()
            elif command.command == "play":
                self.status = "running"
                if not self.clock or self.clock.done():
                    self.clock = asyncio.create_task(self.run_clock())
            elif command.command == "pause":
                self.status = "paused"
            elif command.command == "reset":
                self.status = "paused"
                self.source_mode = "replay"
                self.generation += 1
                self.sequence = 47
                self.history.clear(); self.chart.clear(); self.assessment_chart.clear(); self.incidents.clear(); self.actions.clear(); self.injections.clear(); self.health.clear()
                self.regional_event = None
                self.warmup()
            self.state_version += 1
            with self.db:
                self.db.execute("INSERT INTO runs VALUES (?,?,?)", (self.run_id, self.generation, json.dumps({"status": self.status, "sequence": self.sequence, "speed": self.speed})))
            await self.publish("reset" if command.command in ("reset", "set_source") else "update")
            result = self.snapshot(self.run_id)
        if command.command == "set_source" and command.source_mode == "live":
            return await self.step()
        return result

    async def inject(self, specs: list[InjectionSpec]):
        if not 1 <= len(specs) <= 8:
            raise HTTPException(422, "Batch must contain 1 to 8 faults")
        async with self.lock:
            occupied = {(i.station_id, i.variable) for i in self.injections if i.status in ("scheduled", "active") and i.end_sequence > self.sequence + 1}
            keys = [(s.station_id, s.variable) for s in specs]
            conflict = next((key for key in keys if keys.count(key) > 1 or key in occupied), None)
            if conflict:
                raise HTTPException(409, f"Conflicting fault for {conflict[0]} / {conflict[1]} at upcoming frame {self.sequence + 1}; cancel the existing fault or choose another station-variable pair")
            valid = {s["station_id"] for s in self.source.stations}
            if any(s.station_id not in valid for s in specs):
                raise HTTPException(422, "Unknown station")
            start = self.sequence + 1
            created = [Injection(**s.model_dump(), injection_id=str(uuid.uuid4()), start_sequence=start, end_sequence=start + s.duration_samples, remaining_samples=s.duration_samples) for s in specs]
            self.injections.extend(created)
            with self.db:
                self.db.executemany("INSERT INTO injections VALUES (?,?,?,?)", [(self.run_id, self.generation, i.injection_id, i.model_dump_json()) for i in created])
            self.state_version += 1
            await self.publish()
            return self.snapshot(self.run_id)

    async def regional(self, duration_samples):
        async with self.lock:
            if self.source_mode != "replay":
                raise HTTPException(409, "Regional scenario is replay-only")
            if self.regional_event and self.sequence < self.regional_event["end_sequence"]:
                raise HTTPException(409, "Regional scenario already active")
            self.regional_event = {"name": "coherent_weather_change", "start_sequence": self.sequence + 1, "end_sequence": self.sequence + duration_samples + 1, "duration_samples": duration_samples}
            self.state_version += 1
            await self.publish()
            return self.snapshot(self.run_id)

    async def act(self, incident_id, action):
        async with self.lock:
            incident = self.incidents.get(incident_id)
            if not incident:
                raise HTTPException(404, "Unknown incident")
            status = {"acknowledge": "acknowledged", "confirm_genuine": "confirmed_genuine", "confirm_fault": "confirmed_fault", "maintenance_complete": "resolved"}.get(action)
            if status is None:
                raise HTTPException(422, "Unknown action")
            incident.status = status
            if action == "maintenance_complete":
                incident.task_status = "Maintained"
            item = Action(action_id=str(uuid.uuid4()), incident_id=incident_id, action=action, timestamp=now())
            self.actions.append(item)
            with self.db:
                if action == "maintenance_complete":
                    self.db.execute("UPDATE maintenance_tasks SET status='Maintained',updated_at=?,completed_at=? WHERE incident_id=?", (now(), now(), incident_id))
                self.db.execute("INSERT INTO operator_actions VALUES (?,?,?,?)", (self.run_id, self.generation, item.action_id, item.model_dump_json()))
                self.db.execute("INSERT INTO incidents VALUES (?,?,?,?)", (self.run_id, self.generation, incident_id, incident.model_dump_json()))
            self.state_version += 1
            await self.publish()
            return self.snapshot(self.run_id)

    async def cancel(self, injection_id):
        async with self.lock:
            injection = next((i for i in self.injections if i.injection_id == injection_id), None)
            if not injection:
                raise HTTPException(404, "Unknown injection")
            if injection.status not in ("scheduled", "active"):
                raise HTTPException(409, "Injection has ended")
            injection.status = "cancelled"
            injection.remaining_samples = 0
            self.state_version += 1
            await self.publish()
            return self.snapshot(self.run_id)
