import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable


MigrationFunc = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationFunc


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
           version INTEGER PRIMARY KEY,
           name TEXT NOT NULL,
           applied_at TEXT NOT NULL
        )"""
    )


def migration_status(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_migration_table(conn)
    applied = {
        int(row["version"]): {"version": int(row["version"]), "name": row["name"], "applied_at": row["applied_at"]}
        for row in conn.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY version").fetchall()
    }
    pending = [
        {"version": migration.version, "name": migration.name}
        for migration in MIGRATIONS
        if migration.version not in applied
    ]
    return {
        "current_version": max(applied.keys(), default=0),
        "latest_version": latest_schema_version(),
        "applied": list(applied.values()),
        "pending": pending,
    }


def apply_migrations(conn: sqlite3.Connection) -> list[dict[str, object]]:
    ensure_migration_table(conn)
    applied_versions = {int(row["version"]) for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    applied_now: list[dict[str, object]] = []
    for migration in MIGRATIONS:
        if migration.version in applied_versions:
            continue
        migration.apply(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.name, now_iso()),
        )
        applied_now.append({"version": migration.version, "name": migration.name})
    return applied_now


def latest_schema_version() -> int:
    return MIGRATIONS[-1].version if MIGRATIONS else 0


def _capture_daemon_columns(conn: sqlite3.Connection) -> None:
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
    ensure_columns(
        conn,
        "capture_jobs",
        {
            "progress": "REAL NOT NULL DEFAULT 0",
            "cancel_requested_at": "TEXT",
            "cancel_reason": "TEXT",
            "cancel_mode": "TEXT",
        },
    )


def _core_indexes(conn: sqlite3.Connection) -> None:
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_images_captured_at ON images (captured_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_images_day_captured ON images (day_key, captured_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_images_mode_captured ON images (mode, captured_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_capture_jobs_status_created ON capture_jobs (status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_processing_jobs_status_created ON processing_jobs (status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_night_products_day_type ON night_products (day_key, type)",
        "CREATE INDEX IF NOT EXISTS idx_logs_created ON logs (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_events_delivery_created ON events (delivered_at, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_camera_profiles_camera_mode ON camera_profiles (camera_id, mode)",
    ]
    for statement in indexes:
        conn.execute(statement)


def _schedule_split_sun_angles(conn: sqlite3.Connection) -> None:
    ensure_columns(
        conn,
        "capture_schedule",
        {
            "start_sun_angle": "REAL",
            "end_sun_angle": "REAL",
        },
    )
    conn.execute("UPDATE capture_schedule SET start_sun_angle=COALESCE(start_sun_angle, sun_angle), end_sun_angle=COALESCE(end_sun_angle, sun_angle)")


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "capture_daemon_job_columns", _capture_daemon_columns),
    Migration(2, "core_query_indexes", _core_indexes),
    Migration(3, "schedule_split_sun_angles", _schedule_split_sun_angles),
)
