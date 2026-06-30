from __future__ import annotations

from typing import Any

from ..db import json_loads, row_to_dict


POST_CAPTURE_TRIGGER = "post_capture"
POST_CAPTURE_FLOW_ID = "builtin.post_capture"
BUILTIN_MODULE_IDS = {"builtin.overlay"}


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
