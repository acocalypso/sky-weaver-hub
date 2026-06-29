import sqlite3
from pathlib import Path


def test_init_db_records_schema_migrations(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SKYWEAVER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SKYWEAVER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("SKYWEAVER_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SKYWEAVER_DB", str(tmp_path / "data" / "skyweaver.db"))
    monkeypatch.setenv("SKYWEAVER_SECRET_KEY", "test-secret-key-with-at-least-32-bytes")

    from skyweaver.config import get_settings
    from skyweaver.db import init_db, session
    from skyweaver.migrations import latest_schema_version

    get_settings.cache_clear()
    init_db()

    with session() as conn:
        versions = [row["version"] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
        index_names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}

    assert versions == list(range(1, latest_schema_version() + 1))
    assert "idx_images_day_captured" in index_names
    assert "idx_capture_jobs_status_created" in index_names


def test_migration_upgrade_backfills_legacy_capture_columns(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE capture_state (id INTEGER PRIMARY KEY CHECK (id = 1), status TEXT NOT NULL, current_mode TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE capture_jobs (id TEXT PRIMARY KEY, type TEXT NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL, created_at TEXT NOT NULL)"
        )

    from skyweaver.migrate import upgrade
    from skyweaver.migrations import latest_schema_version

    result = upgrade(db_path)
    assert [item["version"] for item in result["applied"]] == list(range(1, latest_schema_version() + 1))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        capture_state_columns = {row["name"] for row in conn.execute("PRAGMA table_info(capture_state)").fetchall()}
        capture_job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(capture_jobs)").fetchall()}
        applied_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]

    assert "daemon_heartbeat_at" in capture_state_columns
    assert "daemon_last_success_at" in capture_state_columns
    assert "progress" in capture_job_columns
    assert "cancel_mode" in capture_job_columns
    assert applied_count == latest_schema_version()


def test_migration_upgrade_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "skyweaver.db"

    from skyweaver.migrate import status, upgrade

    first = upgrade(db_path)
    second = upgrade(db_path)
    current = status(db_path)

    assert first["applied"]
    assert second["applied"] == []
    assert current["pending"] == []
