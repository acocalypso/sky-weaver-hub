import argparse
import json
from pathlib import Path

from .config import get_settings
from .db import SCHEMA, session
from .migrations import apply_migrations, migration_status


def upgrade(db_path: Path | None = None) -> dict[str, object]:
    with session(db_path) as conn:
        conn.executescript(SCHEMA)
        applied = apply_migrations(conn)
        status = migration_status(conn)
    return {"applied": applied, "status": status}


def status(db_path: Path | None = None) -> dict[str, object]:
    with session(db_path) as conn:
        conn.executescript(SCHEMA)
        return migration_status(conn)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Sky Weaver SQLite schema migrations.")
    parser.add_argument("command", choices=["status", "upgrade"], help="Migration command to run.")
    parser.add_argument("--db", type=Path, default=None, help="Optional SQLite database path. Defaults to SKYWEAVER_DB.")
    args = parser.parse_args()

    if args.command == "upgrade":
        result = upgrade(args.db)
    else:
        result = status(args.db)

    db_path = args.db or get_settings().db_path
    print(json.dumps({"database": str(db_path), **result}, indent=2))


if __name__ == "__main__":
    main()
