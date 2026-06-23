import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .config import Settings, get_settings
from .security import hash_password


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'admin', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, key_hash TEXT NOT NULL, prefix TEXT NOT NULL,
  scopes TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, last_used_at TEXT,
  created_at TEXT NOT NULL, expires_at TEXT
);
CREATE TABLE IF NOT EXISTS cameras (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, adapter TEXT NOT NULL, device_id TEXT,
  model TEXT, serial TEXT, enabled INTEGER NOT NULL DEFAULT 1, is_primary INTEGER NOT NULL DEFAULT 0,
  capabilities TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS camera_profiles (
  id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, name TEXT NOT NULL, mode TEXT NOT NULL,
  settings TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS system_settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS capture_schedule (
  id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, start_mode TEXT NOT NULL DEFAULT 'sun_angle',
  end_mode TEXT NOT NULL DEFAULT 'sun_angle', sun_angle REAL NOT NULL DEFAULT -6,
  fixed_start_time TEXT, fixed_end_time TEXT, timezone TEXT NOT NULL DEFAULT 'UTC',
  latitude REAL NOT NULL DEFAULT 0, longitude REAL NOT NULL DEFAULT 0,
  interval_seconds INTEGER NOT NULL DEFAULT 30, exposure_ramping_enabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS capture_state (
  id INTEGER PRIMARY KEY CHECK (id = 1), status TEXT NOT NULL, current_mode TEXT NOT NULL,
  active_camera_id TEXT, last_image_id TEXT, last_error TEXT, started_at TEXT,
  daemon_heartbeat_at TEXT, daemon_pid INTEGER, daemon_last_claimed_job_id TEXT,
  daemon_last_claimed_job_type TEXT, daemon_last_claimed_at TEXT, daemon_last_success_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS capture_jobs (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL,
  result TEXT, error TEXT, progress REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS images (
  id TEXT PRIMARY KEY, camera_id TEXT, captured_at TEXT NOT NULL, day_key TEXT NOT NULL,
  mode TEXT NOT NULL, file_path TEXT NOT NULL, public_url TEXT, thumbnail_path TEXT,
  format TEXT NOT NULL, width INTEGER, height INTEGER, size_bytes INTEGER, exposure_ms REAL,
  gain REAL, temperature_c REAL, mean_brightness REAL, star_count INTEGER, cloud_score REAL,
  bad_image INTEGER NOT NULL DEFAULT 0, dark_frame_applied INTEGER NOT NULL DEFAULT 0,
  overlay_applied INTEGER NOT NULL DEFAULT 0, metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processing_jobs (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, status TEXT NOT NULL, input TEXT NOT NULL,
  output TEXT, error TEXT, progress REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  started_at TEXT, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS night_products (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, day_key TEXT NOT NULL, file_path TEXT,
  thumbnail_path TEXT, status TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS remote_targets (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL, config_encrypted TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plugin_modules (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, version TEXT, author TEXT,
  module_path TEXT, enabled INTEGER NOT NULL DEFAULT 0, trusted INTEGER NOT NULL DEFAULT 0,
  settings_schema TEXT NOT NULL DEFAULT '{}', settings TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS module_flows (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, trigger TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  module_order TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS logs (
  id TEXT PRIMARY KEY, level TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL,
  context TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
  delivered_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def json_loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or get_settings().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def init_db(path: Path | None = None) -> None:
    settings = get_settings()
    with session(path) as conn:
        conn.executescript(SCHEMA)
        ensure_columns(
            conn,
            "capture_state",
            {
                "daemon_heartbeat_at": "TEXT",
                "daemon_pid": "INTEGER",
                "daemon_last_claimed_job_id": "TEXT",
                "daemon_last_claimed_job_type": "TEXT",
                "daemon_last_claimed_at": "TEXT",
                "daemon_last_success_at": "TEXT",
            },
        )
        ensure_columns(conn, "capture_jobs", {"progress": "REAL NOT NULL DEFAULT 0"})
        seed_defaults(conn, settings)


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def seed_defaults(conn: sqlite3.Connection, settings: Settings) -> None:
    ts = now_iso()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        password_hash = settings.admin_password_hash or hash_password(settings.admin_password or "skyweaver-change-me")
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, 'admin', ?, ?)",
            (new_id(), settings.admin_username, password_hash, ts, ts),
        )
        log(conn, "warning", "security", "Created bootstrap admin; change password during setup", {"username": settings.admin_username})
    if conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0] == 0:
        camera_id = new_id()
        adapter = settings.primary_camera_adapter if settings.primary_camera_adapter in {"mock", "rpicam", "libcamera", "zwo", "gphoto2", "v4l2", "webcam", "indi", "custom_command"} else "mock"
        conn.execute(
            """INSERT INTO cameras (id, name, adapter, device_id, model, enabled, is_primary, capabilities, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?)""",
            (
                camera_id,
                "Primary all-sky camera" if adapter != "mock" else "Mock all-sky camera",
                adapter,
                f"{adapter}://default",
                "Configured during setup" if adapter != "mock" else "Synthetic sky generator",
                json_dumps({"formats": ["jpg", "png"], "controls": ["exposure_ms", "gain"]}),
                ts,
                ts,
            ),
        )
        for mode in ["daytime", "nighttime"]:
            conn.execute(
                "INSERT INTO camera_profiles (id, camera_id, name, mode, settings, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id(), camera_id, mode.title(), mode, json_dumps(default_profile(mode)), ts, ts),
            )
    if conn.execute("SELECT COUNT(*) FROM capture_schedule").fetchone()[0] == 0:
        conn.execute(
            """INSERT INTO capture_schedule
               (id, enabled, sun_angle, timezone, latitude, longitude, interval_seconds, created_at, updated_at)
               VALUES (?, 0, -6, ?, ?, ?, 30, ?, ?)""",
            (new_id(), settings.observatory_timezone, settings.observatory_latitude, settings.observatory_longitude, ts, ts),
        )
    conn.execute(
        """INSERT OR IGNORE INTO capture_state
           (id, status, current_mode, active_camera_id, updated_at)
           VALUES (1, 'idle', 'manual', (SELECT id FROM cameras WHERE is_primary=1 LIMIT 1), ?)""",
        (ts,),
    )
    for key, value in default_settings(settings).items():
        conn.execute(
            "INSERT OR IGNORE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json_dumps(value), ts),
        )


def default_profile(mode: str) -> dict[str, Any]:
    night = mode == "nighttime"
    return {
        "capture_enabled": True,
        "save_enabled": True,
        "auto_exposure": not night,
        "max_auto_exposure_ms": 30000,
        "manual_exposure_ms": 10000 if night else 10,
        "mean_target": 0.28,
        "mean_threshold": 0.08,
        "delay_seconds": 5 if night else 30,
        "auto_gain": not night,
        "max_auto_gain": 16,
        "gain": 4.0 if night else 1.0,
        "stretch_amount": 0.0,
        "stretch_midpoint": 0.5,
        "binning": 1,
        "auto_white_balance": True,
        "red_balance": 1.0,
        "blue_balance": 1.0,
        "frames_to_skip": 0,
        "cooling": False,
        "target_temperature_c": None,
        "tuning_file": None,
    }


def default_settings(settings: Settings | None = None) -> dict[str, Any]:
    observatory = {
        "name": settings.observatory_name if settings else "Sky Weaver Observatory",
        "latitude": settings.observatory_latitude if settings else 0,
        "longitude": settings.observatory_longitude if settings else 0,
        "timezone": settings.observatory_timezone if settings else "UTC",
    }
    return {
        "observatory": observatory,
        "storage": {"images": "./data/images", "videos": "./data/videos", "retention_days": 30, "min_free_gb": 2},
        "public_page": {"enabled": settings.public_page_enabled if settings else True, "refresh_seconds": 30, "iframe_enabled": True},
        "security": {"cors_origins": ["http://localhost:8080"], "first_setup_required": settings.first_setup_required if settings else True},
        "processing": {"thumbnails": True, "keogram": True, "startrails": True, "timelapse": True},
    }


def log(conn: sqlite3.Connection, level: str, source: str, message: str, context: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO logs (id, level, source, message, context, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), level, source, message, json_dumps(context or {}), now_iso()),
    )


def event(conn: sqlite3.Connection, type_: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    item = {"id": new_id(), "type": type_, "payload": payload or {}, "created_at": now_iso()}
    conn.execute(
        "INSERT INTO events (id, type, payload, created_at) VALUES (?, ?, ?, ?)",
        (item["id"], item["type"], json_dumps(item["payload"]), item["created_at"]),
    )
    return item
