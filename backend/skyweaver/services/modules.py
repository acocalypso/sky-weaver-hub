from __future__ import annotations

import re
from typing import Any

from ..db import json_dumps, json_loads, now_iso, row_to_dict


POST_CAPTURE_TRIGGER = "post_capture"
POST_CAPTURE_FLOW_ID = "builtin.post_capture"
BUILTIN_MODULE_IDS = {"builtin.overlay"}
MODULE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,80}$")


def decode_module_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key in ("settings_schema", "settings", "module_order"):
        if key in out and isinstance(out[key], str):
            out[key] = json_loads(out[key], out[key])
    for key in ("enabled", "trusted"):
        if key in out and isinstance(out.get(key), int):
            out[key] = bool(out[key])
    return out


def default_post_capture_flow(ts: str) -> dict[str, Any]:
    return {
        "id": POST_CAPTURE_FLOW_ID,
        "name": "Post-capture processing",
        "trigger": POST_CAPTURE_TRIGGER,
        "enabled": 1,
        "module_order": ["builtin.overlay"],
        "created_at": ts,
        "updated_at": ts,
    }


def normalize_module_order(value: Any) -> list[str]:
    if isinstance(value, str):
        value = json_loads(value, [])
    if not isinstance(value, list):
        raise ValueError("module_order must be an array")
    seen: set[str] = set()
    order: list[str] = []
    for item in value:
        module_id = str(item).strip()
        if not module_id or module_id in seen:
            continue
        seen.add(module_id)
        order.append(module_id)
    return order


def validate_module_order(conn, value: Any) -> list[str]:
    order = normalize_module_order(value)
    for module_id in order:
        row = decode_module_row(row_to_dict(conn.execute("SELECT * FROM plugin_modules WHERE id=?", (module_id,)).fetchone()))
        if not row:
            raise LookupError(f"Module not found: {module_id}")
        if row.get("module_path") or module_id not in BUILTIN_MODULE_IDS:
            raise PermissionError("Custom modules cannot run until sandboxing and signing are implemented")
        if not row.get("trusted"):
            raise PermissionError(f"Module is not trusted: {module_id}")
    return order


def validate_external_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Module manifest must be an object")
    module_id = str(payload.get("id", "")).strip()
    if not MODULE_ID_RE.match(module_id):
        raise ValueError("Module id must be 3-81 lowercase letters, numbers, dots, underscores, or dashes")
    if module_id.startswith("builtin."):
        raise ValueError("External modules cannot use the builtin namespace")
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Module name is required")
    settings_schema = payload.get("settings_schema", {})
    if not isinstance(settings_schema, dict):
        raise ValueError("settings_schema must be an object")
    settings = payload.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    capabilities = payload.get("capabilities", [])
    if capabilities is None:
        capabilities = []
    if not isinstance(capabilities, list):
        raise ValueError("capabilities must be an array")
    return {
        "id": module_id,
        "name": name[:120],
        "description": str(payload.get("description", "")).strip()[:500] or None,
        "version": str(payload.get("version", "0.0.0")).strip()[:64] or "0.0.0",
        "author": str(payload.get("author", "")).strip()[:120] or None,
        "settings_schema": settings_schema,
        "settings": {**settings, "_manifest": {"capabilities": [str(item)[:80] for item in capabilities[:32]]}},
    }


def register_external_module(conn, payload: dict[str, Any]) -> dict[str, Any]:
    manifest = validate_external_manifest(payload)
    ts = now_iso()
    module_path = f"external:{manifest['id']}"
    conn.execute(
        """INSERT INTO plugin_modules
           (id, name, description, version, author, module_path, enabled, trusted, settings_schema, settings, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name,
             description=excluded.description,
             version=excluded.version,
             author=excluded.author,
             module_path=excluded.module_path,
             enabled=0,
             trusted=0,
             settings_schema=excluded.settings_schema,
             settings=excluded.settings,
             updated_at=excluded.updated_at""",
        (
            manifest["id"],
            manifest["name"],
            manifest["description"],
            manifest["version"],
            manifest["author"],
            module_path,
            json_dumps(manifest["settings_schema"]),
            json_dumps(manifest["settings"]),
            ts,
            ts,
        ),
    )
    return decode_module_row(row_to_dict(conn.execute("SELECT * FROM plugin_modules WHERE id=?", (manifest["id"],)).fetchone())) or {}


def enabled_flow_module_order(conn, trigger: str) -> list[str]:
    row = decode_module_row(
        row_to_dict(
            conn.execute(
                "SELECT * FROM module_flows WHERE trigger=? AND enabled=1 ORDER BY name LIMIT 1",
                (trigger,),
            ).fetchone()
        )
    )
    if not row:
        return []
    try:
        return validate_module_order(conn, row.get("module_order", []))
    except (LookupError, PermissionError, ValueError):
        return []


def module_enabled_for_trigger(conn, trigger: str, module_id: str) -> bool:
    order = enabled_flow_module_order(conn, trigger)
    if not order:
        return False
    return module_id in order


def run_flow_preview(conn, flow_id: str) -> dict[str, Any]:
    row = decode_module_row(row_to_dict(conn.execute("SELECT * FROM module_flows WHERE id=?", (flow_id,)).fetchone()))
    if not row:
        raise LookupError("Module flow not found")
    order = validate_module_order(conn, row.get("module_order", []))
    modules = []
    for module_id in order:
        module = decode_module_row(row_to_dict(conn.execute("SELECT * FROM plugin_modules WHERE id=?", (module_id,)).fetchone())) or {}
        modules.append(
            {
                "id": module_id,
                "name": module.get("name", module_id),
                "enabled": bool(module.get("enabled")),
                "trusted": bool(module.get("trusted")),
                "status": "ready" if row.get("enabled") and module.get("enabled") else "skipped",
            }
        )
    return {
        "id": flow_id,
        "trigger": row.get("trigger"),
        "status": "completed",
        "enabled": bool(row.get("enabled")),
        "modules": modules,
    }
