"""Ensure public demo accounts match the login page without logging passwords."""
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.data import PreparedSource
from app.operations import Operations, hash_password, verify_password


def main():
    path = Path(os.getenv("ATMOTRUST_DATABASE_PATH", str(ROOT / "backend/atmotrust.sqlite3")))
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    ops = Operations(db, PreparedSource().stations)
    accounts = json.loads((ROOT / "frontend/src/demo_accounts.json").read_text(encoding="utf-8"))
    for role in ("authority", "employee"):
        account = accounts[role]
        username, password = account["username"], account["password"]
        if len(password) < 12:
            raise ValueError("Demo passwords must have at least 12 characters")
        existing = db.execute("SELECT id,role,password_hash FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            if existing[1] != role:
                raise ValueError(f"Demo username {username} has the wrong role")
            if not verify_password(password, existing[2]):
                with db:
                    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), existing[0]))
                    db.execute("DELETE FROM sessions WHERE user_id=?", (existing[0],))
                print(f"{role} demo password rotated; prior sessions revoked")
            else:
                print(f"{role} demo account ready")
            continue
        user = ops.create_user(username, account["display_name"], role, password)
        if role == "employee":
            for station in ops.stations():
                ops.assign(user["id"], station["station_id"])
        print(f"{role} demo account created")
    db.close()


if __name__ == "__main__":
    main()
