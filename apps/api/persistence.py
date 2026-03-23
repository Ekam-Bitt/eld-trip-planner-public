from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Iterator, Sequence
from uuid import uuid4


VALID_ROLES = {"admin", "dispatcher", "driver"}
PBKDF2_ITERATIONS = int(os.getenv("AUTH_PBKDF2_ITERATIONS", "390000"))
SESSION_TTL_HOURS = int(os.getenv("AUTH_SESSION_TTL_HOURS", "24"))


@dataclass(frozen=True)
class UserRecord:
    id: str
    organization_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class SessionRecord:
    token: str
    expires_at: str


@dataclass(frozen=True)
class DriverProfileRecord:
    user_id: str
    organization_id: str
    carrier_name: str
    main_office_address: str
    home_terminal_address: str
    truck_trailer_numbers: str
    cycle_rule: str
    is_onboarding_complete: bool
    created_at: str
    updated_at: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_password: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded_password.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(rounds),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row["name"]) == column_name for row in rows)


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'dispatcher', 'driver')),
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS driver_profiles (
                user_id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                carrier_name TEXT NOT NULL DEFAULT '',
                main_office_address TEXT NOT NULL DEFAULT '',
                home_terminal_address TEXT NOT NULL DEFAULT '',
                truck_trailer_numbers TEXT NOT NULL DEFAULT '',
                cycle_rule TEXT NOT NULL DEFAULT '70' CHECK (cycle_rule IN ('60', '70')),
                is_onboarding_complete INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS trip_runs (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                driver_user_id TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                cycle TEXT NOT NULL,
                current_location TEXT NOT NULL,
                pickup_location TEXT NOT NULL,
                dropoff_location TEXT NOT NULL,
                current_cycle_used_hours REAL NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (driver_user_id) REFERENCES users(id) ON DELETE RESTRICT,
                FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS daily_logs (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                driver_user_id TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL,
                trip_run_id TEXT,
                log_date TEXT NOT NULL,
                cycle TEXT NOT NULL,
                values_json TEXT NOT NULL,
                recap_json TEXT NOT NULL,
                compliance_json TEXT NOT NULL,
                timeline_events_json TEXT NOT NULL,
                svg_path TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (driver_user_id) REFERENCES users(id) ON DELETE RESTRICT,
                FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT,
                FOREIGN KEY (trip_run_id) REFERENCES trip_runs(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_org_role
                ON users (organization_id, role);
            CREATE INDEX IF NOT EXISTS idx_driver_profiles_org_user
                ON driver_profiles (organization_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_trip_runs_org_created
                ON trip_runs (organization_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_trip_runs_org_driver_created
                ON trip_runs (organization_id, driver_user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_org_date
                ON daily_logs (organization_id, log_date);
            CREATE INDEX IF NOT EXISTS idx_logs_org_driver_date
                ON daily_logs (organization_id, driver_user_id, log_date);
            """
        )
        if not _table_has_column(conn, "daily_logs", "trip_run_id"):
            conn.execute("ALTER TABLE daily_logs ADD COLUMN trip_run_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_trip_run_date ON daily_logs (trip_run_id, log_date)")
        conn.commit()


def row_to_user(row: sqlite3.Row | None) -> UserRecord | None:
    if row is None:
        return None
    return UserRecord(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        email=str(row["email"]),
        full_name=str(row["full_name"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
    )


def row_to_driver_profile(row: sqlite3.Row | None) -> DriverProfileRecord | None:
    if row is None:
        return None
    return DriverProfileRecord(
        user_id=str(row["user_id"]),
        organization_id=str(row["organization_id"]),
        carrier_name=str(row["carrier_name"]),
        main_office_address=str(row["main_office_address"]),
        home_terminal_address=str(row["home_terminal_address"]),
        truck_trailer_numbers=str(row["truck_trailer_numbers"]),
        cycle_rule=str(row["cycle_rule"]),
        is_onboarding_complete=bool(row["is_onboarding_complete"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def users_exist(db_path: Path) -> bool:
    with connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None


def get_user_by_email(db_path: Path, email: str) -> tuple[UserRecord | None, str | None]:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, organization_id, email, full_name, role, password_hash, is_active, created_at
            FROM users
            WHERE email = ?
            """,
            (normalize_email(email),),
        ).fetchone()

    if row is None:
        return None, None

    return row_to_user(row), str(row["password_hash"])


def get_user_by_id(db_path: Path, user_id: str) -> UserRecord | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, organization_id, email, full_name, role, is_active, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_user(row)


def create_bootstrap_admin(
    db_path: Path,
    organization_name: str,
    full_name: str,
    email: str,
    password_hash_value: str,
) -> UserRecord:
    if users_exist(db_path):
        raise ValueError("Bootstrap already completed; users already exist.")

    organization_id = uuid4().hex
    user_id = uuid4().hex
    timestamp = utc_now_iso()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO organizations (id, name, created_at)
            VALUES (?, ?, ?)
            """,
            (organization_id, organization_name.strip(), timestamp),
        )
        conn.execute(
            """
            INSERT INTO users (id, organization_id, email, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, 'admin', ?, 1, ?)
            """,
            (
                user_id,
                organization_id,
                normalize_email(email),
                full_name.strip(),
                password_hash_value,
                timestamp,
            ),
        )
        conn.commit()

    user = get_user_by_id(db_path, user_id)
    if user is None:
        raise RuntimeError("Failed to create bootstrap user.")
    return user


def create_user_with_organization(
    db_path: Path,
    organization_name: str,
    full_name: str,
    email: str,
    role: str,
    password_hash_value: str,
) -> UserRecord:
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        raise ValueError("Invalid role.")

    organization_id = uuid4().hex
    user_id = uuid4().hex
    timestamp = utc_now_iso()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO organizations (id, name, created_at)
            VALUES (?, ?, ?)
            """,
            (organization_id, organization_name.strip(), timestamp),
        )
        conn.execute(
            """
            INSERT INTO users (id, organization_id, email, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                user_id,
                organization_id,
                normalize_email(email),
                full_name.strip(),
                normalized_role,
                password_hash_value,
                timestamp,
            ),
        )
        conn.commit()

    user = get_user_by_id(db_path, user_id)
    if user is None:
        raise RuntimeError("Failed to create standalone user.")
    return user


def create_user(
    db_path: Path,
    organization_id: str,
    full_name: str,
    email: str,
    role: str,
    password_hash_value: str,
) -> UserRecord:
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        raise ValueError("Invalid role.")

    user_id = uuid4().hex
    timestamp = utc_now_iso()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (id, organization_id, email, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                user_id,
                organization_id,
                normalize_email(email),
                full_name.strip(),
                normalized_role,
                password_hash_value,
                timestamp,
            ),
        )
        conn.commit()

    user = get_user_by_id(db_path, user_id)
    if user is None:
        raise RuntimeError("Failed to create user.")
    return user


def get_driver_profile(db_path: Path, user_id: str) -> DriverProfileRecord | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                user_id,
                organization_id,
                carrier_name,
                main_office_address,
                home_terminal_address,
                truck_trailer_numbers,
                cycle_rule,
                is_onboarding_complete,
                created_at,
                updated_at
            FROM driver_profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_driver_profile(row)


def upsert_driver_profile(
    db_path: Path,
    *,
    organization_id: str,
    user_id: str,
    carrier_name: str,
    main_office_address: str,
    home_terminal_address: str,
    truck_trailer_numbers: str,
    cycle_rule: str = "70",
    is_onboarding_complete: bool = True,
) -> DriverProfileRecord:
    normalized_cycle_rule = str(cycle_rule).strip()
    if normalized_cycle_rule not in {"60", "70"}:
        raise ValueError("cycle_rule must be either '60' or '70'.")

    timestamp = utc_now_iso()

    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT created_at FROM driver_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        created_at = str(existing["created_at"]) if existing is not None else timestamp
        conn.execute(
            """
            INSERT INTO driver_profiles (
                user_id,
                organization_id,
                carrier_name,
                main_office_address,
                home_terminal_address,
                truck_trailer_numbers,
                cycle_rule,
                is_onboarding_complete,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                organization_id = excluded.organization_id,
                carrier_name = excluded.carrier_name,
                main_office_address = excluded.main_office_address,
                home_terminal_address = excluded.home_terminal_address,
                truck_trailer_numbers = excluded.truck_trailer_numbers,
                cycle_rule = excluded.cycle_rule,
                is_onboarding_complete = excluded.is_onboarding_complete,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                organization_id,
                carrier_name.strip(),
                main_office_address.strip(),
                home_terminal_address.strip(),
                truck_trailer_numbers.strip(),
                normalized_cycle_rule,
                1 if is_onboarding_complete else 0,
                created_at,
                timestamp,
            ),
        )
        conn.commit()

    profile = get_driver_profile(db_path, user_id)
    if profile is None:
        raise RuntimeError("Failed to create driver profile.")
    return profile


def list_users(
    db_path: Path,
    organization_id: str,
    role: str | None = None,
) -> list[UserRecord]:
    params: list[Any] = [organization_id]
    query = """
        SELECT id, organization_id, email, full_name, role, is_active, created_at
        FROM users
        WHERE organization_id = ?
    """

    if role:
        params.append(role.strip().lower())
        query += " AND role = ?"

    query += " ORDER BY created_at DESC"

    with connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return [user for row in rows if (user := row_to_user(row)) is not None]


def create_session(db_path: Path, user_id: str) -> SessionRecord:
    token = secrets.token_urlsafe(48)
    token_hash = hash_session_token(token)
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = created_at + timedelta(hours=SESSION_TTL_HOURS)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions (token_hash, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                token_hash,
                user_id,
                expires_at.isoformat(),
                created_at.isoformat(),
            ),
        )
        conn.commit()

    return SessionRecord(
        token=token,
        expires_at=expires_at.isoformat(),
    )


def delete_session(db_path: Path, token: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (hash_session_token(token),),
        )
        conn.commit()


def prune_expired_sessions(db_path: Path) -> None:
    now = utc_now_iso()
    with connect(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.commit()


def get_user_by_session_token(db_path: Path, token: str) -> UserRecord | None:
    prune_expired_sessions(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT u.id, u.organization_id, u.email, u.full_name, u.role, u.is_active, u.created_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1
            """,
            (
                hash_session_token(token),
                utc_now_iso(),
            ),
        ).fetchone()

    return row_to_user(row)


def create_trip_run(
    db_path: Path,
    organization_id: str,
    driver_user_id: str,
    created_by_user_id: str,
    cycle: str,
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used_hours: float,
    start_date: str,
    end_date: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    record_id = uuid4().hex
    created_at = utc_now_iso()
    plan_json = json.dumps(plan, separators=(",", ":"), ensure_ascii=True)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trip_runs (
                id,
                organization_id,
                driver_user_id,
                created_by_user_id,
                cycle,
                current_location,
                pickup_location,
                dropoff_location,
                current_cycle_used_hours,
                start_date,
                end_date,
                plan_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                organization_id,
                driver_user_id,
                created_by_user_id,
                cycle,
                current_location,
                pickup_location,
                dropoff_location,
                float(current_cycle_used_hours),
                start_date,
                end_date,
                plan_json,
                created_at,
            ),
        )
        conn.commit()

    return {
        "id": record_id,
        "organization_id": organization_id,
        "driver_user_id": driver_user_id,
        "created_by_user_id": created_by_user_id,
        "cycle": cycle,
        "current_location": current_location,
        "pickup_location": pickup_location,
        "dropoff_location": dropoff_location,
        "current_cycle_used_hours": round(float(current_cycle_used_hours), 2),
        "start_date": start_date,
        "end_date": end_date,
        "plan": plan,
        "created_at": created_at,
    }


def _parse_trip_run_row(row: sqlite3.Row) -> dict[str, Any]:
    plan = _parse_json_column(row, "plan_json") or {}
    route = plan.get("route") if isinstance(plan, dict) else {}
    stops = plan.get("stops") if isinstance(plan, dict) else []
    locations = plan.get("locations") if isinstance(plan, dict) else {}
    planned_daily_logs = plan.get("daily_logs") if isinstance(plan, dict) else []
    days_count = plan.get("days_count") if isinstance(plan, dict) else None

    if not isinstance(route, dict):
        route = {}
    if not isinstance(stops, list):
        stops = []
    if not isinstance(locations, dict):
        locations = {}
    if not isinstance(planned_daily_logs, list):
        planned_daily_logs = []
    if not isinstance(days_count, int):
        days_count = len(planned_daily_logs)

    return {
        "id": str(row["id"]),
        "organization_id": str(row["organization_id"]),
        "driver_user_id": str(row["driver_user_id"]),
        "driver_name": str(row["driver_name"]),
        "driver_email": str(row["driver_email"]),
        "created_by_user_id": str(row["created_by_user_id"]),
        "created_by_name": str(row["created_by_name"]),
        "cycle": str(row["cycle"]),
        "current_location": str(row["current_location"]),
        "pickup_location": str(row["pickup_location"]),
        "dropoff_location": str(row["dropoff_location"]),
        "current_cycle_used_hours": round(float(row["current_cycle_used_hours"]), 2),
        "start_date": str(row["start_date"]),
        "end_date": str(row["end_date"]),
        "plan": plan if isinstance(plan, dict) else {},
        "route": route,
        "stops": stops,
        "locations": locations,
        "planned_daily_logs": planned_daily_logs,
        "days_count": days_count,
        "created_at": str(row["created_at"]),
    }


def list_trip_runs(
    db_path: Path,
    organization_id: str,
    limit: int = 20,
    driver_user_id: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [organization_id]
    query = """
        SELECT
            t.id,
            t.organization_id,
            t.driver_user_id,
            t.created_by_user_id,
            t.cycle,
            t.current_location,
            t.pickup_location,
            t.dropoff_location,
            t.current_cycle_used_hours,
            t.start_date,
            t.end_date,
            t.plan_json,
            t.created_at,
            d.full_name AS driver_name,
            d.email AS driver_email,
            c.full_name AS created_by_name
        FROM trip_runs t
        JOIN users d ON d.id = t.driver_user_id
        JOIN users c ON c.id = t.created_by_user_id
        WHERE t.organization_id = ?
    """

    if driver_user_id:
        query += " AND t.driver_user_id = ?"
        params.append(driver_user_id)

    query += " ORDER BY t.created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 100)))

    with connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return [_parse_trip_run_row(row) for row in rows]


def get_trip_run(db_path: Path, record_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                t.id,
                t.organization_id,
                t.driver_user_id,
                t.created_by_user_id,
                t.cycle,
                t.current_location,
                t.pickup_location,
                t.dropoff_location,
                t.current_cycle_used_hours,
                t.start_date,
                t.end_date,
                t.plan_json,
                t.created_at,
                d.full_name AS driver_name,
                d.email AS driver_email,
                c.full_name AS created_by_name
            FROM trip_runs t
            JOIN users d ON d.id = t.driver_user_id
            JOIN users c ON c.id = t.created_by_user_id
            WHERE t.id = ?
            """,
            (record_id,),
        ).fetchone()

    if row is None:
        return None
    return _parse_trip_run_row(row)


def create_daily_log(
    db_path: Path,
    organization_id: str,
    driver_user_id: str,
    created_by_user_id: str,
    trip_run_id: str | None,
    log_date: str,
    cycle: str,
    values: dict[str, Any],
    recap: dict[str, Any],
    compliance: dict[str, Any],
    timeline_events: list[dict[str, Any]],
    svg_path: str,
    pdf_path: str,
) -> dict[str, Any]:
    record_id = uuid4().hex
    created_at = utc_now_iso()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO daily_logs (
                id,
                organization_id,
                driver_user_id,
                created_by_user_id,
                trip_run_id,
                log_date,
                cycle,
                values_json,
                recap_json,
                compliance_json,
                timeline_events_json,
                svg_path,
                pdf_path,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                organization_id,
                driver_user_id,
                created_by_user_id,
                trip_run_id,
                log_date,
                cycle,
                json.dumps(values, separators=(",", ":"), ensure_ascii=True),
                json.dumps(recap, separators=(",", ":"), ensure_ascii=True),
                json.dumps(compliance, separators=(",", ":"), ensure_ascii=True),
                json.dumps(timeline_events, separators=(",", ":"), ensure_ascii=True),
                svg_path,
                pdf_path,
                created_at,
            ),
        )
        conn.commit()

    return {
        "id": record_id,
        "organization_id": organization_id,
        "driver_user_id": driver_user_id,
        "created_by_user_id": created_by_user_id,
        "trip_run_id": trip_run_id,
        "log_date": log_date,
        "cycle": cycle,
        "svg_path": svg_path,
        "pdf_path": pdf_path,
        "created_at": created_at,
    }


def _parse_json_column(row: sqlite3.Row, key: str) -> Any:
    raw = row[key]
    try:
        return json.loads(raw)
    except Exception:
        return None


def list_daily_logs(
    db_path: Path,
    organization_id: str,
    limit: int = 25,
    driver_user_id: str | None = None,
    trip_run_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [organization_id]
    query = """
        SELECT
            l.id,
            l.organization_id,
            l.driver_user_id,
            l.created_by_user_id,
            l.trip_run_id,
            l.log_date,
            l.cycle,
            l.compliance_json,
            l.svg_path,
            l.pdf_path,
            l.created_at,
            d.full_name AS driver_name,
            d.email AS driver_email,
            c.full_name AS created_by_name
        FROM daily_logs l
        JOIN users d ON d.id = l.driver_user_id
        JOIN users c ON c.id = l.created_by_user_id
        WHERE l.organization_id = ?
    """

    if driver_user_id:
        query += " AND l.driver_user_id = ?"
        params.append(driver_user_id)
    if trip_run_id:
        query += " AND l.trip_run_id = ?"
        params.append(trip_run_id)
    if start_date:
        query += " AND l.log_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND l.log_date <= ?"
        params.append(end_date)

    query += " ORDER BY l.log_date DESC, l.created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 200)))

    with connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        compliance = _parse_json_column(row, "compliance_json") or {}
        items.append(
            {
                "id": str(row["id"]),
                "organization_id": str(row["organization_id"]),
                "driver_user_id": str(row["driver_user_id"]),
                "driver_name": str(row["driver_name"]),
                "driver_email": str(row["driver_email"]),
                "created_by_user_id": str(row["created_by_user_id"]),
                "created_by_name": str(row["created_by_name"]),
                "trip_run_id": str(row["trip_run_id"]) if row["trip_run_id"] is not None else None,
                "log_date": str(row["log_date"]),
                "cycle": str(row["cycle"]),
                "is_legal_today": bool(compliance.get("is_legal_today", True)),
                "is_legal_tomorrow": bool(compliance.get("is_legal_tomorrow", True)),
                "available_hours_tomorrow": compliance.get("available_hours_tomorrow"),
                "svg_path": str(row["svg_path"]),
                "pdf_path": str(row["pdf_path"]),
                "created_at": str(row["created_at"]),
            }
        )
    return items


def summarize_trip_run_logs(
    db_path: Path,
    organization_id: str,
    trip_run_ids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    normalized_trip_ids = [str(trip_id).strip() for trip_id in trip_run_ids if str(trip_id).strip()]
    if not normalized_trip_ids:
        return {}

    placeholders = ",".join(["?"] * len(normalized_trip_ids))
    params: list[Any] = [organization_id, *normalized_trip_ids]

    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT trip_run_id, compliance_json
            FROM daily_logs
            WHERE organization_id = ?
              AND trip_run_id IN ({placeholders})
            """,
            tuple(params),
        ).fetchall()

    summaries: dict[str, dict[str, Any]] = {}
    for row in rows:
        trip_run_id = row["trip_run_id"]
        if trip_run_id is None:
            continue
        trip_run_id_value = str(trip_run_id)

        summary = summaries.setdefault(
            trip_run_id_value,
            {
                "generated_sheet_count": 0,
                "all_logs_legal": True,
                "non_compliant_count": 0,
            },
        )

        summary["generated_sheet_count"] += 1
        compliance = _parse_json_column(row, "compliance_json") or {}
        is_legal = bool(compliance.get("is_legal_today", True)) and bool(
            compliance.get("is_legal_tomorrow", True)
        )
        if not is_legal:
            summary["all_logs_legal"] = False
            summary["non_compliant_count"] += 1

    return summaries


def get_daily_log(db_path: Path, record_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                l.id,
                l.organization_id,
                l.driver_user_id,
                l.created_by_user_id,
                l.trip_run_id,
                l.log_date,
                l.cycle,
                l.values_json,
                l.recap_json,
                l.compliance_json,
                l.timeline_events_json,
                l.svg_path,
                l.pdf_path,
                l.created_at,
                d.full_name AS driver_name,
                d.email AS driver_email,
                c.full_name AS created_by_name
            FROM daily_logs l
            JOIN users d ON d.id = l.driver_user_id
            JOIN users c ON c.id = l.created_by_user_id
            WHERE l.id = ?
            """,
            (record_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": str(row["id"]),
        "organization_id": str(row["organization_id"]),
        "driver_user_id": str(row["driver_user_id"]),
        "driver_name": str(row["driver_name"]),
        "driver_email": str(row["driver_email"]),
        "created_by_user_id": str(row["created_by_user_id"]),
        "created_by_name": str(row["created_by_name"]),
        "trip_run_id": str(row["trip_run_id"]) if row["trip_run_id"] is not None else None,
        "log_date": str(row["log_date"]),
        "cycle": str(row["cycle"]),
        "values": _parse_json_column(row, "values_json") or {},
        "recap": _parse_json_column(row, "recap_json") or {},
        "compliance": _parse_json_column(row, "compliance_json") or {},
        "timeline_events": _parse_json_column(row, "timeline_events_json") or [],
        "svg_path": str(row["svg_path"]),
        "pdf_path": str(row["pdf_path"]),
        "created_at": str(row["created_at"]),
    }
