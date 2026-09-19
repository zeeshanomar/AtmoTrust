"""Operational identity, assignments, maintenance and alert records."""
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from .schema import now


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('authority','employee')), password_hash TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 expires_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stations (
 station_id TEXT PRIMARY KEY, name TEXT NOT NULL, pole_id TEXT NOT NULL UNIQUE,
 latitude REAL NOT NULL, longitude REAL NOT NULL, criticality REAL NOT NULL,
 maintenance_email TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employee_assignments (
 user_id TEXT NOT NULL REFERENCES users(id), station_id TEXT NOT NULL REFERENCES stations(station_id),
 PRIMARY KEY(user_id,station_id)
);
CREATE TABLE IF NOT EXISTS operational_incidents (
 incident_id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(station_id),
 variable TEXT NOT NULL, opened_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
 fault_type TEXT NOT NULL, severity TEXT NOT NULL, assessment_json TEXT NOT NULL,
 run_id TEXT NOT NULL, generation INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS maintenance_tasks (
 incident_id TEXT PRIMARY KEY REFERENCES operational_incidents(incident_id),
 assignee_id TEXT REFERENCES users(id), status TEXT NOT NULL DEFAULT 'Assigned',
 updated_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS maintenance_notes (
 id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES maintenance_tasks(incident_id),
 author_id TEXT NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS authority_notifications (
 id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES operational_incidents(incident_id),
 station_id TEXT NOT NULL REFERENCES stations(station_id), actor_user_id TEXT NOT NULL REFERENCES users(id),
 event_type TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
 created_at TEXT NOT NULL, read_at TEXT
);
CREATE INDEX IF NOT EXISTS authority_notifications_recent ON authority_notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS authority_notifications_unread ON authority_notifications(read_at,created_at DESC);
CREATE TABLE IF NOT EXISTS email_settings (
 station_id TEXT PRIMARY KEY REFERENCES stations(station_id), enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS email_deliveries (
 id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES operational_incidents(incident_id),
 station_id TEXT NOT NULL REFERENCES stations(station_id), recipient TEXT,
 reason TEXT NOT NULL, severity TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','sent','failed','suppressed','outbox')),
 safe_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS email_once_per_reason ON email_deliveries(incident_id,reason);
CREATE INDEX IF NOT EXISTS tasks_by_assignee ON maintenance_tasks(assignee_id,status);
CREATE INDEX IF NOT EXISTS incidents_by_station ON operational_incidents(station_id,opened_at);
CREATE INDEX IF NOT EXISTS email_by_incident ON email_deliveries(incident_id,created_at);
CREATE TABLE IF NOT EXISTS model_metadata (version TEXT PRIMARY KEY, manifest_json TEXT NOT NULL, loaded_at TEXT NOT NULL);
"""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 390_000)
    return f"pbkdf2_sha256$390000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, expected = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def evidence_confidence(value: float) -> str:
    band = "Weak" if value < 0.4 else "Moderate" if value < 0.7 else "Strong"
    return f"{band} · {value:.2f}"


class Operations:
    def __init__(self, db: sqlite3.Connection, stations: list[dict]):
        self.db = db
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        with self.db:
            for station in stations:
                self.db.execute("INSERT OR IGNORE INTO stations VALUES (?,?,?,?,?,?,?,?)", (
                    station["station_id"], station["name"], station.get("pole_id", f"POLE-{station['station_id']}"),
                    station["latitude"], station["longitude"], station["criticality"], None, now()))
                self.db.execute("INSERT OR IGNORE INTO email_settings VALUES (?,1)", (station["station_id"],))

    def stations(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM stations ORDER BY station_id")]

    def user(self, user_id):
        row = self.db.execute("SELECT id,username,display_name,role,active FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def users(self):
        return [dict(row) for row in self.db.execute("SELECT id,username,display_name,role,active,created_at FROM users ORDER BY username")]

    def create_user(self, username, display_name, role, password):
        if role not in ("authority", "employee") or len(password) < 12:
            raise ValueError("Role or password invalid; use at least 12 password characters")
        user_id = str(uuid.uuid4())
        with self.db:
            self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?)", (user_id, username.strip(), display_name.strip(), role, hash_password(password), 1, now()))
        return self.user(user_id)

    def set_active(self, user_id, active):
        with self.db:
            self.db.execute("UPDATE users SET active=? WHERE id=? AND role='employee'", (int(active), user_id))
            if not active:
                self.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return self.user(user_id)

    def login(self, username, password):
        row = self.db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], expiry, now()))
        return token, self.user(row["id"])

    def session(self, token):
        if not token:
            return None
        row = self.db.execute("SELECT u.id,u.username,u.display_name,u.role,u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1", (hashlib.sha256(token.encode()).hexdigest(), now())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        if token:
            with self.db:
                self.db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def assignments(self, user_id=None):
        sql = "SELECT a.user_id,a.station_id,u.display_name,s.pole_id FROM employee_assignments a JOIN users u ON u.id=a.user_id JOIN stations s ON s.station_id=a.station_id"
        args = ()
        if user_id:
            sql += " WHERE a.user_id=?"
            args = (user_id,)
        return [dict(row) for row in self.db.execute(sql + " ORDER BY a.station_id", args)]

    def assign(self, user_id, station_id, assigned=True):
        user = self.user(user_id)
        station = self.db.execute("SELECT 1 FROM stations WHERE station_id=?", (station_id,)).fetchone()
        if not user or user["role"] != "employee" or not station:
            raise ValueError("Unknown employee or station")
        with self.db:
            if assigned:
                self.db.execute("INSERT OR IGNORE INTO employee_assignments VALUES (?,?)", (user_id, station_id))
                self.db.execute("UPDATE maintenance_tasks SET assignee_id=? WHERE assignee_id IS NULL AND incident_id IN (SELECT incident_id FROM operational_incidents WHERE station_id=?)", (user_id, station_id))
            else:
                self.db.execute("DELETE FROM employee_assignments WHERE user_id=? AND station_id=?", (user_id, station_id))
                replacement = self.db.execute("SELECT user_id FROM employee_assignments WHERE station_id=? ORDER BY user_id LIMIT 1", (station_id,)).fetchone()
                self.db.execute("UPDATE maintenance_tasks SET assignee_id=? WHERE assignee_id=? AND incident_id IN (SELECT incident_id FROM operational_incidents WHERE station_id=?)", (replacement[0] if replacement else None, user_id, station_id))

    def update_station(self, station_id, name, pole_id, maintenance_email, criticality):
        if maintenance_email and (len(maintenance_email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", maintenance_email)):
            raise ValueError("Invalid maintenance email address")
        with self.db:
            cursor = self.db.execute("UPDATE stations SET name=?,pole_id=?,maintenance_email=?,criticality=?,updated_at=? WHERE station_id=?", (name, pole_id, maintenance_email or None, criticality, now(), station_id))
        if not cursor.rowcount:
            raise ValueError("Unknown station")
        return dict(self.db.execute("SELECT * FROM stations WHERE station_id=?", (station_id,)).fetchone())

    def record_incident(self, incident, assessment, run_id, generation):
        with self.db:
            self.db.execute("INSERT INTO operational_incidents VALUES (?,?,?,?,?,?,?,?,?,?)", (
                incident.incident_id, incident.station_id, incident.variable, incident.opened_at,
                incident.last_seen_at, incident.fault_type, incident.severity, assessment.model_dump_json(), run_id, generation))
            assignee = self.db.execute("SELECT user_id FROM employee_assignments a JOIN users u ON u.id=a.user_id WHERE a.station_id=? AND u.active=1 ORDER BY user_id LIMIT 1", (incident.station_id,)).fetchone()
            self.db.execute("INSERT OR IGNORE INTO maintenance_tasks VALUES (?,?,?,?,?)", (incident.incident_id, assignee[0] if assignee else None, "Assigned", now(), None))

    def update_incident(self, incident, assessment):
        with self.db:
            self.db.execute("UPDATE operational_incidents SET last_seen_at=?,fault_type=?,severity=?,assessment_json=? WHERE incident_id=?", (incident.last_seen_at, incident.fault_type, incident.severity, assessment.model_dump_json(), incident.incident_id))

    def tasks(self, user=None):
        import json
        sql = "SELECT t.*,i.station_id,i.variable,i.fault_type,i.severity,i.opened_at,i.last_seen_at,i.assessment_json,s.name AS station_name,s.pole_id,u.display_name AS assignee_name FROM maintenance_tasks t JOIN operational_incidents i ON i.incident_id=t.incident_id JOIN stations s ON s.station_id=i.station_id LEFT JOIN users u ON u.id=t.assignee_id"
        args = ()
        if user and user["role"] == "employee":
            sql += " WHERE t.assignee_id=? AND i.station_id IN (SELECT station_id FROM employee_assignments WHERE user_id=?)"
            args = (user["id"], user["id"])
        rows = []
        for row in self.db.execute(sql + " ORDER BY i.opened_at DESC", args):
            item = dict(row)
            assessment = json.loads(item.pop("assessment_json"))
            item["trust_score"] = assessment.get("trust_score")
            item["confidence"] = assessment.get("confidence")
            item["assessment_status"] = assessment.get("assessment_status")
            item["expected_value"] = assessment.get("expected_value")
            item["explanation"] = assessment.get("explanation")
            item["resolution"] = assessment.get("resolution")
            rows.append(item)
        return rows

    def task(self, incident_id, user=None):
        return next((task for task in self.tasks(user) if task["incident_id"] == incident_id), None)

    def update_task(self, incident_id, user, status, note=None):
        task = self.task(incident_id, user)
        if not task:
            return None
        if user["role"] == "employee":
            allowed = {"Assigned": "Maintenance In Progress", "Reopened": "Maintenance In Progress", "Maintenance In Progress": "Maintained"}
            if allowed.get(task["status"]) != status:
                raise ValueError("Invalid maintenance transition")
        elif status not in ("Assigned", "Maintenance In Progress", "Maintained", "Reopened"):
            raise ValueError("Invalid maintenance status")
        with self.db:
            self.db.execute("UPDATE maintenance_tasks SET status=?,updated_at=?,completed_at=? WHERE incident_id=?", (status, now(), now() if status == "Maintained" else None, incident_id))
            if note:
                self.db.execute("INSERT INTO maintenance_notes VALUES (?,?,?,?,?)", (str(uuid.uuid4()), incident_id, user["id"], note[:2000], now()))
            if user["role"] == "employee":
                event_type = "maintenance_completed" if status == "Maintained" else "maintenance_started"
                self._notify_employee_action(task, user, event_type, task["status"], status, note)
        return self.task(incident_id, user)

    def assign_task(self, incident_id, user_id):
        row = self.db.execute("SELECT i.station_id FROM maintenance_tasks t JOIN operational_incidents i ON i.incident_id=t.incident_id WHERE t.incident_id=?", (incident_id,)).fetchone()
        eligible = self.db.execute("SELECT 1 FROM employee_assignments a JOIN users u ON u.id=a.user_id WHERE a.user_id=? AND a.station_id=? AND u.active=1 AND u.role='employee'", (user_id, row[0] if row else None)).fetchone()
        if not row or not eligible:
            raise ValueError("Employee must be active and assigned to this station")
        with self.db:
            self.db.execute("UPDATE maintenance_tasks SET assignee_id=?,updated_at=? WHERE incident_id=?", (user_id, now(), incident_id))
        return self.task(incident_id)

    def add_note(self, incident_id, user, body):
        task = self.task(incident_id, user)
        if not task:
            return None
        with self.db:
            self.db.execute("INSERT INTO maintenance_notes VALUES (?,?,?,?,?)", (str(uuid.uuid4()), incident_id, user["id"], body[:2000], now()))
            if user["role"] == "employee":
                self._notify_employee_action(task, user, "maintenance_note", task["status"], task["status"], body)
        return self.notes(incident_id, user)

    def _notify_employee_action(self, task, user, event_type, old_status, new_status, note):
        title = {"maintenance_started": "Maintenance started", "maintenance_completed": "Maintenance completed", "maintenance_note": "New maintenance note"}[event_type]
        context = f"{user['display_name']} · {task['station_name']} ({task['pole_id']}) · {task['variable']} · probable {task['fault_type']} · incident {task['incident_id'][:8]}"
        detail = f"Status: {old_status} → {new_status}." if old_status != new_status else f"Status: {new_status}."
        preview = " ".join(note.split())[:160] if note else ""
        if preview:
            detail += f" Note: {preview}"
        self.db.execute("INSERT INTO authority_notifications VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), task["incident_id"], task["station_id"], user["id"], event_type, title, f"{context}. {detail}", now(), None))

    def authority_notifications(self):
        items = [dict(row) for row in self.db.execute("SELECT * FROM authority_notifications ORDER BY created_at DESC,id DESC LIMIT 50")]
        unread_count = self.db.execute("SELECT COUNT(*) FROM authority_notifications WHERE read_at IS NULL").fetchone()[0]
        return {"items": items, "unread_count": unread_count}

    def read_authority_notification(self, notification_id):
        with self.db:
            self.db.execute("UPDATE authority_notifications SET read_at=COALESCE(read_at,?) WHERE id=?", (now(), notification_id))
        row = self.db.execute("SELECT * FROM authority_notifications WHERE id=?", (notification_id,)).fetchone()
        return dict(row) if row else None

    def read_all_authority_notifications(self):
        with self.db:
            self.db.execute("UPDATE authority_notifications SET read_at=? WHERE read_at IS NULL", (now(),))
        return self.authority_notifications()

    def notes(self, incident_id, user):
        if not self.task(incident_id, user):
            return None
        return [dict(row) for row in self.db.execute("SELECT n.id,n.body,n.created_at,u.display_name AS author FROM maintenance_notes n JOIN users u ON u.id=n.author_id WHERE incident_id=? ORDER BY n.created_at", (incident_id,))]

    def queue_email(self, incident, assessment, reason):
        station = self.db.execute("SELECT * FROM stations WHERE station_id=?", (incident.station_id,)).fetchone()
        enabled = self.db.execute("SELECT enabled FROM email_settings WHERE station_id=?", (incident.station_id,)).fetchone()
        recipient = station["maintenance_email"] if station else None
        task = self.db.execute("SELECT assignee_id FROM maintenance_tasks WHERE incident_id=?", (incident.incident_id,)).fetchone()
        frontend_url = os.getenv("ATMOTRUST_FRONTEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://127.0.0.1:8000"
        task_link = f"{frontend_url.rstrip('/')}/employee?task={incident.incident_id}" if task and task[0] else "Not assigned"
        subject = f"[AtmoTrust] {incident.severity} {incident.fault_type} detected at {station['name']}"
        body = "\n".join((f"Station: {station['name']} ({incident.station_id})", f"Pole: {station['pole_id']}", f"Variable: {incident.variable}", f"Probable fault: {incident.fault_type}", f"Severity: {incident.severity}", f"Trust Score: {assessment.trust_score if assessment.trust_score is not None else 'N/A'}", f"Evidence Confidence: {evidence_confidence(assessment.confidence) if assessment.assessment_status == 'complete' else 'N/A'}", f"Observed: {assessment.observed_value if hasattr(assessment,'observed_value') else 'N/A'}", f"Expected: {assessment.expected_value if assessment.expected_value is not None else 'N/A'}", f"Detected: {assessment.timestamp}", f"Explanation: {assessment.explanation}", f"Resolution: {assessment.resolution}", f"Incident ID: {incident.incident_id}", f"Employee task: {task_link}"))
        status = "queued" if recipient and enabled and enabled[0] else "suppressed"
        try:
            with self.db:
                self.db.execute("INSERT INTO email_deliveries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), incident.incident_id, incident.station_id, recipient, reason, incident.severity, subject, body, status, None if status == "queued" else "No enabled station recipient", now(), now()))
        except sqlite3.IntegrityError:
            return None
        return dict(self.db.execute("SELECT * FROM email_deliveries WHERE incident_id=? AND reason=?", (incident.incident_id, reason)).fetchone())

    def emails(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM email_deliveries ORDER BY created_at DESC")]

    def deliver(self, delivery_id):
        row = self.db.execute("SELECT * FROM email_deliveries WHERE id=?", (delivery_id,)).fetchone()
        if not row or row["status"] != "queued":
            return None
        host = os.getenv("ATMOTRUST_SMTP_HOST", "")
        enabled = os.getenv("ATMOTRUST_EMAIL_ENABLED", "false").lower() == "true"
        if not host or not enabled:
            status, error = "outbox", "SMTP disabled or unconfigured; stored in development outbox"
        else:
            try:
                message = EmailMessage()
                message["From"] = os.getenv("ATMOTRUST_SMTP_SENDER", "")
                message["To"] = row["recipient"]
                message["Subject"] = row["subject"]
                message.set_content(row["body"])
                port = int(os.getenv("ATMOTRUST_SMTP_PORT", "587"))
                with smtplib.SMTP(host, port, timeout=8) as smtp:
                    smtp.starttls()
                    username = os.getenv("ATMOTRUST_SMTP_USERNAME", "")
                    if username:
                        smtp.login(username, os.getenv("ATMOTRUST_SMTP_PASSWORD", ""))
                    smtp.send_message(message)
                status, error = "sent", None
            except (OSError, smtplib.SMTPException, ValueError):
                status, error = "failed", "SMTP delivery failed; check server configuration and logs"
        with self.db:
            self.db.execute("UPDATE email_deliveries SET status=?,safe_error=?,updated_at=? WHERE id=?", (status, error, now(), delivery_id))
        return status
