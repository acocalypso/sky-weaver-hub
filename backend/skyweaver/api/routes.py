import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..camera.registry import adapters, get_adapter
from ..config import get_settings
from ..db import default_profile, event, json_dumps, json_loads, log, new_id, now_iso, row_to_dict, session
from ..rate_limit import InMemoryRateLimiter, RateLimitStatus
from ..security import create_api_key, hash_password, make_token, verify_password
from ..services.capture import CaptureCommand, all_rows, cleanup_images_by_retention, configured_image_retention_days, count_files, create_capture_job, current_schedule, decode_row, delete_image_files, enqueue_capture, get_primary_camera, public_latest_payload, publish_latest_image, read_latest_payload, scheduled_capture_timing, system_metrics
from ..services.processing import cleanup_products_by_retention, delete_product_files
from ..services.schedule import active_window
from .deps import current_principal, require_scope
from .responses import ok

router = APIRouter(prefix="/api/v1", tags=["api-v1"])

SERVICE_UNITS = {
    "skyweaver": "skyweaver.target",
    "skyweaver.target": "skyweaver.target",
    "skyweaver-api": "skyweaver-api.service",
    "skyweaver-api.service": "skyweaver-api.service",
    "skyweaver-capture": "skyweaver-capture.service",
    "skyweaver-capture.service": "skyweaver-capture.service",
    "skyweaver-worker": "skyweaver-worker.service",
    "skyweaver-worker.service": "skyweaver-worker.service",
}
SERVICE_ACTIONS = {"start", "stop", "restart"}
BOOTSTRAP_PASSWORD = "skyweaver-change-me"
SERVICE_DETAIL_PROPERTIES = [
    "Id",
    "Description",
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "MainPID",
    "ExecMainStatus",
    "ExecMainCode",
    "ExecMainStartTimestamp",
    "ExecMainExitTimestamp",
    "Result",
    "Restart",
    "NRestarts",
    "ActiveEnterTimestamp",
    "InactiveEnterTimestamp",
    "StateChangeTimestamp",
    "FragmentPath",
    "DropInPaths",
]
SENSITIVE_WORDS = ("password", "passwd", "secret", "token", "api_key", "apikey", "key_hash", "authorization")
AUTH_RATE_LIMIT_MAX_FAILURES = 5
AUTH_RATE_LIMIT_WINDOW_SECONDS = 300
auth_rate_limiter = InMemoryRateLimiter(AUTH_RATE_LIMIT_MAX_FAILURES, AUTH_RATE_LIMIT_WINDOW_SECONDS)


class LoginRequest(BaseModel):
    username: str
    password: str


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["read:status", "read:images"])
    expires_at: str | None = None


class CameraCreate(BaseModel):
    name: str
    adapter: str = "mock"
    device_id: str | None = None
    model: str | None = None
    serial: str | None = None
    enabled: bool = True
    is_primary: bool = False


class CameraPatch(BaseModel):
    name: str | None = None
    adapter: str | None = None
    device_id: str | None = None
    model: str | None = None
    serial: str | None = None
    enabled: bool | None = None
    is_primary: bool | None = None


class CaptureBody(BaseModel):
    camera_id: str | None = None
    exposure_ms: float = 1000
    gain: float = 1.0
    width: int | None = 1280
    height: int | None = 960
    format: str = "jpg"
    mode: str = "manual"
    settings: dict[str, Any] = Field(default_factory=dict)


class SettingsPatch(BaseModel):
    values: dict[str, Any]


class SetupComplete(BaseModel):
    admin_password: str | None = Field(default=None, min_length=8, max_length=128)
    observatory_name: str = Field(default="Sky Weaver Observatory", min_length=1, max_length=120)
    latitude: float = Field(default=0, ge=-90, le=90)
    longitude: float = Field(default=0, ge=-180, le=180)
    timezone: str = "UTC"
    public_page_enabled: bool = True
    primary_camera_id: str | None = None


def password_issues(password: str) -> list[str]:
    issues: list[str] = []
    if password == BOOTSTRAP_PASSWORD:
        issues.append("Choose a password different from the bootstrap default.")
    if len(password.encode("utf-8")) > 72:
        issues.append("Use a password that is 72 bytes or fewer.")
    if len(password) < 12:
        issues.append("Use at least 12 characters.")
    if password.lower() in {"password", "admin", "skyweaver", "skyweaver123", "skyweaver-change-me"}:
        issues.append("Avoid common or product-default passwords.")
    categories = sum([
        any(ch.islower() for ch in password),
        any(ch.isupper() for ch in password),
        any(ch.isdigit() for ch in password),
        any(not ch.isalnum() for ch in password),
    ])
    if categories < 3 and len(password) < 20:
        issues.append("Use a mix of character types or a longer passphrase.")
    return issues


def is_bootstrap_password_hash(password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return verify_password(BOOTSTRAP_PASSWORD, password_hash)
    except Exception:
        return False


def client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def audit_user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:160] if value else None


def rate_limit_key(action: str, request: Request, identifier: str) -> str:
    settings = get_settings()
    return f"{settings.db_path}:{action}:{client_host(request)}:{identifier.lower()}"


def audit_auth_event(conn, level: str, action: str, message: str, request: Request, identifier: str, status: RateLimitStatus | None = None, reason: str | None = None) -> None:
    context: dict[str, Any] = {
        "action": action,
        "identifier": identifier[:120],
        "client_host": client_host(request),
    }
    user_agent = audit_user_agent(request)
    if user_agent:
        context["user_agent"] = user_agent
    if reason:
        context["reason"] = reason
    if status:
        context["failure_count"] = status.failure_count
        context["rate_limited"] = not status.allowed
        if status.retry_after_seconds:
            context["retry_after_seconds"] = status.retry_after_seconds
    log(conn, level, "auth", message, context)


def principal_context(principal: dict[str, Any]) -> dict[str, Any]:
    context = {
        "principal_type": principal.get("type", "user"),
        "principal_id": principal.get("id"),
        "principal_username": principal.get("username"),
    }
    scopes = principal.get("scopes")
    if scopes:
        context["principal_scopes"] = sorted(scopes)
    return {key: value for key, value in context.items() if value is not None}


def audit_security_event(
    conn,
    level: str,
    action: str,
    message: str,
    request: Request,
    principal: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> None:
    safe_context: dict[str, Any] = {
        "action": action,
        "client_host": client_host(request),
        **principal_context(principal),
    }
    user_agent = audit_user_agent(request)
    if user_agent:
        safe_context["user_agent"] = user_agent
    if context:
        safe_context.update(context)
    log(conn, level, "security", message, safe_context)


def field_names(values: dict[str, Any]) -> list[str]:
    return sorted(str(key) for key in values)


def settings_keys(values: dict[str, Any]) -> list[str]:
    return sorted(str(key) for key in values)


def profile_settings_keys(payload: dict[str, Any]) -> list[str]:
    settings = payload.get("settings")
    if isinstance(settings, dict):
        return field_names(settings)
    return []


def raise_rate_limited(retry_after_seconds: int) -> None:
    raise HTTPException(
        status_code=429,
        detail="Too many failed attempts. Try again later.",
        headers={"Retry-After": str(retry_after_seconds)},
    )


def enforce_rate_limit(key: str) -> RateLimitStatus:
    status = auth_rate_limiter.check(key)
    if not status.allowed:
        raise_rate_limited(status.retry_after_seconds)
    return status


def record_failed_attempt(key: str) -> RateLimitStatus:
    return auth_rate_limiter.record_failure(key)


class SchedulePut(BaseModel):
    enabled: bool
    start_mode: str = "sun_angle"
    end_mode: str = "sun_angle"
    sun_angle: float = -6
    start_sun_angle: float | None = None
    end_sun_angle: float | None = None
    fixed_start_time: str | None = None
    fixed_end_time: str | None = None
    timezone: str = "UTC"
    latitude: float = 0
    longitude: float = 0
    interval_seconds: int = 30
    exposure_ramping_enabled: bool = False


@router.get("/health")
def health():
    return ok({"status": "ok", "service": "skyweaver-api", "version": "0.1.0"})


@router.get("/status")
def status(_principal: Annotated[dict, Depends(require_scope("read:status"))]):
    with session() as conn:
        state = decode_row(row_to_dict(conn.execute("SELECT * FROM capture_state WHERE id=1").fetchone()))
        latest = decode_row(row_to_dict(conn.execute("SELECT * FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()))
        camera = decode_row(row_to_dict(conn.execute("SELECT * FROM cameras WHERE id=?", (state.get("active_camera_id"),)).fetchone())) if state else None
    return ok({"capture": state, "camera": camera, "latest_image": latest})


@router.get("/system/metrics")
def metrics(_principal: Annotated[dict, Depends(require_scope("read:status"))]):
    return ok(system_metrics())


@router.get("/system/services")
def services(_principal: Annotated[dict, Depends(require_scope("read:status"))]):
    return ok(service_rows())


@router.get("/system/services/{name}")
def service_detail(name: str, journal_lines: int = Query(80, ge=0, le=500), _principal: Annotated[dict, Depends(require_scope("read:status"))] = None):
    return ok(service_detail_row(name, journal_lines))


def service_rows() -> list[dict[str, Any]]:
    with session() as conn:
        state = decode_row(row_to_dict(conn.execute(
            "SELECT daemon_heartbeat_at, daemon_pid, daemon_last_claimed_job_id, daemon_last_claimed_job_type, daemon_last_claimed_at, daemon_last_success_at FROM capture_state WHERE id=1"
        ).fetchone())) or {}
    heartbeat = state.get("daemon_heartbeat_at")
    age_seconds = None
    capture_status = "idle"
    if heartbeat:
        try:
            age_seconds = int((datetime.now(UTC) - datetime.fromisoformat(heartbeat)).total_seconds())
            capture_status = "running" if age_seconds <= 120 else "stale"
        except ValueError:
            capture_status = "unknown"
    return [
        {"name": "skyweaver", "unit": "skyweaver.target", "status": "running", "managed_by": "systemd", "actions": sorted(SERVICE_ACTIONS)},
        {"name": "skyweaver-api", "unit": "skyweaver-api.service", "status": "running", "managed_by": "systemd", "actions": sorted(SERVICE_ACTIONS)},
        {
            "name": "skyweaver-capture",
            "unit": "skyweaver-capture.service",
            "status": capture_status,
            "managed_by": "systemd",
            "actions": sorted(SERVICE_ACTIONS),
            "heartbeat_at": heartbeat,
            "heartbeat_age_seconds": age_seconds,
            "pid": state.get("daemon_pid"),
            "last_claimed_job_id": state.get("daemon_last_claimed_job_id"),
            "last_claimed_job_type": state.get("daemon_last_claimed_job_type"),
            "last_claimed_at": state.get("daemon_last_claimed_at"),
            "last_success_at": state.get("daemon_last_success_at"),
        },
        {"name": "skyweaver-worker", "unit": "skyweaver-worker.service", "status": "idle", "managed_by": "systemd", "actions": sorted(SERVICE_ACTIONS)},
    ]


def redact_operational_text(value: str) -> str:
    if any(word in value.lower() for word in SENSITIVE_WORDS):
        return "[redacted]"
    return value


def parse_systemctl_show(output: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        properties[key] = redact_operational_text(value)
    return properties


def service_unit_history(properties: dict[str, str]) -> dict[str, Any]:
    labels = {
        "ActiveEnterTimestamp": "Entered active",
        "InactiveEnterTimestamp": "Entered inactive",
        "StateChangeTimestamp": "Last state change",
        "ExecMainStartTimestamp": "Main process start",
        "ExecMainExitTimestamp": "Main process exit",
    }
    history = []
    for key, label in labels.items():
        value = properties.get(key, "").strip()
        if value and value.lower() not in {"n/a", "never"}:
            history.append({"label": label, "value": value})
    restarts = properties.get("NRestarts", "")
    return {
        "restarts": int(restarts) if restarts.isdigit() else None,
        "result": properties.get("Result") or None,
        "exec_main_status": properties.get("ExecMainStatus") or None,
        "recent_events": history,
    }


def service_failure_analysis(service: dict[str, Any], properties: dict[str, str], journal: list[str]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    suggestions: list[str] = []
    active_state = properties.get("ActiveState") or service.get("status", "unknown")
    result = properties.get("Result", "")
    exec_status = properties.get("ExecMainStatus", "")
    restart_count = properties.get("NRestarts", "")

    if active_state == "failed":
        findings.append({"level": "error", "message": f"systemd reports ActiveState={active_state}."})
        suggestions.append("Open the recent journal, fix the first reported error, then restart the service.")
    elif active_state in {"inactive", "deactivating"}:
        findings.append({"level": "warning", "message": f"systemd reports ActiveState={active_state}."})
    if result and result not in {"success", "exit-code"}:
        findings.append({"level": "error", "message": f"Last unit result was {result}."})
    if result == "exit-code" or (exec_status and exec_status != "0"):
        findings.append({"level": "error", "message": f"Main process exited with status {exec_status or result}."})
    if restart_count and restart_count not in {"0", "n/a"}:
        findings.append({"level": "warning", "message": f"systemd recorded {restart_count} restart attempt(s)."})
        suggestions.append("Check whether the service is repeatedly failing during startup or after camera access.")
    if service.get("status") == "stale":
        findings.append({"level": "warning", "message": "Capture daemon heartbeat is stale."})
        suggestions.append("Restart skyweaver-capture and verify camera/device permissions if the heartbeat does not recover.")

    important_terms = ("failed", "error", "denied", "permission", "traceback", "exception", "timeout", "fatal")
    matching_journal = [line for line in journal if any(term in line.lower() for term in important_terms)]
    for line in matching_journal[-3:]:
        findings.append({"level": "warning", "message": f"Recent journal signal: {line}"})
    if any("permission" in line.lower() or "denied" in line.lower() for line in matching_journal):
        suggestions.append("Check service user groups, /dev/media* access, DMA heap access, and sudoers permissions.")

    if not findings:
        findings.append({"level": "ok", "message": "No obvious failure signals found in systemd properties or recent journal output."})

    severity = "ok"
    if any(item["level"] == "error" for item in findings):
        severity = "error"
    elif any(item["level"] == "warning" for item in findings):
        severity = "warning"

    summary = {
        "ok": "Service looks healthy from available systemd and journal data.",
        "warning": "Service has warning signals that may need attention.",
        "error": "Service has failure signals that need attention.",
    }[severity]
    return {"severity": severity, "summary": summary, "findings": findings, "suggested_actions": list(dict.fromkeys(suggestions))}


def service_detail_row(name: str, journal_lines: int = 80) -> dict[str, Any]:
    unit = SERVICE_UNITS.get(name)
    if not unit:
        raise HTTPException(404, "Unknown Sky Weaver service")
    service = next((row for row in service_rows() if row["unit"] == unit), {"name": name, "unit": unit, "status": "unknown"})
    detail: dict[str, Any] = {
        "service": service,
        "unit": unit,
        "properties": {},
        "systemctl_status": "unavailable",
        "systemctl_error": None,
        "journal": [],
        "journal_status": "unavailable",
        "journal_error": None,
        "unit_history": {},
        "failure_analysis": {},
    }

    command = systemctl_command()
    if command:
        result = subprocess.run(
            [*command, "show", unit, "--no-pager", f"--property={','.join(SERVICE_DETAIL_PROPERTIES)}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 0:
            detail["systemctl_status"] = "ok"
            detail["properties"] = parse_systemctl_show(result.stdout)
        else:
            detail["systemctl_status"] = "failed"
            detail["systemctl_error"] = redact_operational_text((result.stderr or result.stdout or "systemctl show failed").strip())

    journalctl = shutil.which("journalctl")
    if journalctl and journal_lines > 0:
        result = subprocess.run(
            [journalctl, "-u", unit, "-n", str(journal_lines), "--no-pager", "--output=short-iso"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 0:
            detail["journal_status"] = "ok"
            detail["journal"] = [redact_operational_text(line) for line in result.stdout.splitlines() if line.strip()]
        else:
            detail["journal_status"] = "failed"
            detail["journal_error"] = redact_operational_text((result.stderr or result.stdout or "journalctl failed").strip())
    detail["unit_history"] = service_unit_history(detail["properties"])
    detail["failure_analysis"] = service_failure_analysis(service, detail["properties"], detail["journal"])
    return detail


@router.get("/system/diagnostics")
def diagnostics(_principal: Annotated[dict, Depends(require_scope("read:status"))]):
    settings = get_settings()
    with session() as conn:
        counts = {
            "images": conn.execute("SELECT COUNT(*) FROM images").fetchone()[0],
            "capture_jobs_pending": conn.execute("SELECT COUNT(*) FROM capture_jobs WHERE status='pending'").fetchone()[0],
            "capture_jobs_running": conn.execute("SELECT COUNT(*) FROM capture_jobs WHERE status IN ('claimed', 'running')").fetchone()[0],
            "processing_jobs_pending": conn.execute("SELECT COUNT(*) FROM processing_jobs WHERE status='pending'").fetchone()[0],
            "processing_jobs_running": conn.execute("SELECT COUNT(*) FROM processing_jobs WHERE status IN ('claimed', 'running')").fetchone()[0],
            "products": conn.execute("SELECT COUNT(*) FROM night_products").fetchone()[0],
            "logs": conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0],
        }
        recent_logs = all_rows(conn, "SELECT level, source, message, created_at FROM logs ORDER BY created_at DESC LIMIT 25")
    db_path = settings.db_path
    return ok({
        "generated_at": now_iso(),
        "app": {"name": settings.app_name, "environment": settings.environment, "version": "0.1.0"},
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "paths": {
            "data_dir": str(settings.data_dir),
            "config_dir": str(settings.config_dir),
            "log_dir": str(settings.log_dir),
            "database": str(db_path),
        },
        "database": {"exists": db_path.exists(), "size_bytes": db_path.stat().st_size if db_path.exists() else 0},
        "metrics": system_metrics(),
        "services": service_rows(),
        "counts": counts,
        "recent_logs": recent_logs,
        "redaction": "Secrets, password hashes, API-key hashes, and remote credentials are not included.",
    })


def systemctl_command() -> list[str] | None:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return None
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return [systemctl]
    sudo = shutil.which("sudo")
    if sudo:
        return [sudo, "-n", systemctl]
    return [systemctl]


def run_service_action(name: str, action: str) -> dict[str, str]:
    unit = SERVICE_UNITS.get(name)
    if not unit:
        raise HTTPException(404, "Unknown Sky Weaver service")
    if action not in SERVICE_ACTIONS:
        raise HTTPException(400, "Unsupported service action")
    command = systemctl_command()
    if not command:
        return {"name": name, "unit": unit, "action": action, "status": "unavailable", "note": "systemctl is not available on this host."}

    if unit in {"skyweaver-api.service", "skyweaver.target"} and action in {"stop", "restart"}:
        full_command = [*command, "--no-block", action, unit]
        result = subprocess.run(full_command, capture_output=True, text=True, timeout=20, check=False)
        if result.returncode != 0:
            note = (result.stderr or result.stdout or "systemctl command failed").strip()
            return {"name": name, "unit": unit, "action": action, "status": "failed", "note": note}
        return {"name": name, "unit": unit, "action": action, "status": "queued", "note": f"{action} queued for {unit}."}

    full_command = [*command, action, unit]
    result = subprocess.run(full_command, capture_output=True, text=True, timeout=20, check=False)
    if result.returncode != 0:
        note = (result.stderr or result.stdout or "systemctl command failed").strip()
        return {"name": name, "unit": unit, "action": action, "status": "failed", "note": note}
    return {"name": name, "unit": unit, "action": action, "status": "completed", "note": f"{action} completed for {unit}."}


@router.post("/system/services/{name}/{action}")
def control_service(name: str, action: str, _principal: Annotated[dict, Depends(require_scope("admin"))]):
    return ok(run_service_action(name, action))


@router.post("/system/services/{name}/restart")
def restart_service(name: str, _principal: Annotated[dict, Depends(require_scope("admin"))]):
    return ok(run_service_action(name, "restart"))


@router.get("/logs")
def logs(level: str | None = None, source: str | None = None, limit: int = 200, _principal: dict = Depends(require_scope("read:status"))):
    clauses: list[str] = []
    params: list[Any] = []
    if level:
        clauses.append("level=?")
        params.append(level)
    if source:
        clauses.append("source LIKE ?")
        params.append(f"%{source}%")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with session() as conn:
        rows = all_rows(conn, f"SELECT * FROM logs {where} ORDER BY created_at DESC LIMIT ?", (*params, limit))
    return ok(rows)


@router.post("/auth/login")
def login(body: LoginRequest, request: Request):
    settings = get_settings()
    limit_key = rate_limit_key("login", request, body.username)
    limit_status = auth_rate_limiter.check(limit_key)
    if not limit_status.allowed:
        with session() as conn:
            audit_auth_event(conn, "warning", "login", "Login blocked by rate limit", request, body.username, limit_status, "rate_limited")
        raise_rate_limited(limit_status.retry_after_seconds)
    with session() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
        if not row or not verify_password(body.password, row["password_hash"]):
            failure_status = record_failed_attempt(limit_key)
            audit_auth_event(conn, "warning", "login", "Login failed", request, body.username, failure_status, "invalid_credentials")
            conn.commit()
            if not failure_status.allowed:
                raise_rate_limited(failure_status.retry_after_seconds)
            raise HTTPException(401, "Invalid username or password")
        conn.execute("UPDATE users SET last_login_at=?, updated_at=? WHERE id=?", (now_iso(), now_iso(), row["id"]))
        token = make_token({"sub": row["id"], "username": row["username"], "role": row["role"], "scopes": ["admin"]}, settings.secret_key)
        if limit_status.failure_count:
            audit_auth_event(conn, "info", "login", "Login succeeded after previous failures", request, body.username, limit_status)
    auth_rate_limiter.reset(limit_key)
    return ok({"token": token, "user": {"id": row["id"], "username": row["username"], "role": row["role"]}})


@router.post("/auth/logout")
def logout():
    return ok({"ok": True})


@router.get("/auth/me")
def me(principal: Annotated[dict, Depends(current_principal)]):
    return ok(principal)


@router.get("/setup/status")
def setup_status(principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        settings_rows = {row["key"]: row["value"] for row in all_rows(conn, "SELECT * FROM system_settings")}
        schedule = decode_row(row_to_dict(conn.execute("SELECT * FROM capture_schedule LIMIT 1").fetchone())) or {}
        cameras = all_rows(conn, "SELECT id, name, adapter, device_id, model, is_primary FROM cameras ORDER BY is_primary DESC, created_at")
        user = conn.execute("SELECT password_hash FROM users WHERE id=?", (principal["id"],)).fetchone()
    security = settings_rows.get("security", {})
    observatory = settings_rows.get("observatory", {})
    public_page = settings_rows.get("public_page", {})
    bootstrap_password_active = bool(user and is_bootstrap_password_hash(user["password_hash"]))
    return ok({
        "required": bool(security.get("first_setup_required", False)) or bootstrap_password_active,
        "bootstrap_password_active": bootstrap_password_active,
        "observatory": observatory,
        "public_page": public_page,
        "schedule": schedule,
        "cameras": cameras,
    })


@router.post("/setup/complete")
def setup_complete(body: SetupComplete, request: Request, principal: Annotated[dict, Depends(require_scope("admin"))]):
    limit_key = rate_limit_key("setup", request, principal["id"])
    limit_status = auth_rate_limiter.check(limit_key)
    if not limit_status.allowed:
        with session() as conn:
            audit_auth_event(conn, "warning", "setup", "Setup completion blocked by rate limit", request, principal["id"], limit_status, "rate_limited")
        raise_rate_limited(limit_status.retry_after_seconds)
    if body.admin_password:
        issues = password_issues(body.admin_password)
        if issues:
            with session() as conn:
                failure_status = record_failed_attempt(limit_key)
                audit_auth_event(conn, "warning", "setup", "Setup completion failed", request, principal["id"], failure_status, "password_policy")
            if not failure_status.allowed:
                raise_rate_limited(failure_status.retry_after_seconds)
            raise HTTPException(400, " ".join(issues))
    with session() as conn:
        current_user = conn.execute("SELECT password_hash FROM users WHERE id=?", (principal["id"],)).fetchone()
        if not body.admin_password and current_user and is_bootstrap_password_hash(current_user["password_hash"]):
            failure_status = record_failed_attempt(limit_key)
            audit_auth_event(conn, "warning", "setup", "Setup completion failed", request, principal["id"], failure_status, "bootstrap_password_active")
            conn.commit()
            if not failure_status.allowed:
                raise_rate_limited(failure_status.retry_after_seconds)
            raise HTTPException(400, "Change the bootstrap admin password before completing setup.")
        settings_rows = {row["key"]: row["value"] for row in all_rows(conn, "SELECT * FROM system_settings")}
        security = {**settings_rows.get("security", {}), "first_setup_required": False}
        observatory = {
            "name": body.observatory_name,
            "latitude": body.latitude,
            "longitude": body.longitude,
            "timezone": body.timezone,
        }
        public_page = {**settings_rows.get("public_page", {}), "enabled": body.public_page_enabled}
        for key, value in {"security": security, "observatory": observatory, "public_page": public_page}.items():
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)", (key, json_dumps(value), now_iso()))
        conn.execute(
            "UPDATE capture_schedule SET timezone=?, latitude=?, longitude=?, updated_at=? WHERE id=(SELECT id FROM capture_schedule LIMIT 1)",
            (body.timezone, body.latitude, body.longitude, now_iso()),
        )
        if body.primary_camera_id:
            exists = conn.execute("SELECT id FROM cameras WHERE id=?", (body.primary_camera_id,)).fetchone()
            if not exists:
                failure_status = record_failed_attempt(limit_key)
                audit_auth_event(conn, "warning", "setup", "Setup completion failed", request, principal["id"], failure_status, "primary_camera_not_found")
                conn.commit()
                if not failure_status.allowed:
                    raise_rate_limited(failure_status.retry_after_seconds)
                raise HTTPException(404, "Primary camera not found")
            conn.execute("UPDATE cameras SET is_primary=0")
            conn.execute("UPDATE cameras SET is_primary=1, updated_at=? WHERE id=?", (now_iso(), body.primary_camera_id))
            conn.execute("UPDATE capture_state SET active_camera_id=?, updated_at=? WHERE id=1", (body.primary_camera_id, now_iso()))
        if body.admin_password:
            conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (hash_password(body.admin_password), now_iso(), principal["id"]))
        audit_security_event(
            conn,
            "info",
            "setup_completed",
            "First setup completed",
            request,
            principal,
            {
                "password_changed": bool(body.admin_password),
                "settings_keys": ["observatory", "public_page", "security"],
                "schedule_fields": ["latitude", "longitude", "timezone"],
                "public_page_enabled": body.public_page_enabled,
                "primary_camera_id": body.primary_camera_id,
            },
        )
    auth_rate_limiter.reset(limit_key)
    return ok({"required": False})


@router.patch("/users/me/password")
def change_password(body: LoginRequest, request: Request, principal: Annotated[dict, Depends(current_principal)]):
    issues = password_issues(body.password)
    if issues:
        raise HTTPException(400, " ".join(issues))
    with session() as conn:
        conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (hash_password(body.password), now_iso(), principal["id"]))
        audit_security_event(conn, "info", "password_changed", "Password changed", request, principal, {"target_user_id": principal["id"]})
    return ok({"ok": True})


@router.get("/users")
def users(_principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT id, username, role, created_at, updated_at, last_login_at FROM users ORDER BY username")
    return ok(rows)


@router.post("/users")
def create_user(body: LoginRequest, request: Request, principal: Annotated[dict, Depends(require_scope("admin"))]):
    issues = password_issues(body.password)
    if issues:
        raise HTTPException(400, " ".join(issues))
    with session() as conn:
        user_id = new_id()
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, 'operator', ?, ?)",
            (user_id, body.username, hash_password(body.password), now_iso(), now_iso()),
        )
        audit_security_event(conn, "info", "user_created", "User created", request, principal, {"target_user_id": user_id, "target_username": body.username, "target_role": "operator"})
    return ok({"id": user_id, "username": body.username, "role": "operator"})


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: dict[str, Any], request: Request, principal: Annotated[dict, Depends(require_scope("admin"))]):
    role = payload.get("role")
    if role not in {"admin", "operator", "viewer"}:
        raise HTTPException(400, "Invalid role")
    with session() as conn:
        conn.execute("UPDATE users SET role=?, updated_at=? WHERE id=?", (role, now_iso(), user_id))
        audit_security_event(conn, "info", "user_updated", "User updated", request, principal, {"target_user_id": user_id, "changed_fields": ["role"], "target_role": role})
    return ok({"id": user_id, "role": role})


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request, principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        audit_security_event(conn, "warning", "user_deleted", "User deleted", request, principal, {"target_user_id": user_id})
    return ok({"deleted": user_id})


@router.get("/api-keys")
def api_keys(_principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT id, name, prefix, scopes, enabled, last_used_at, created_at, expires_at FROM api_keys ORDER BY created_at DESC")
    return ok(rows)


@router.post("/api-keys")
def create_key(body: ApiKeyCreate, request: Request, principal: Annotated[dict, Depends(require_scope("admin"))]):
    raw, prefix, hashed = create_api_key()
    with session() as conn:
        item_id = new_id()
        conn.execute(
            "INSERT INTO api_keys (id, name, key_hash, prefix, scopes, enabled, created_at, expires_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (item_id, body.name, hashed, prefix, json_dumps(body.scopes), now_iso(), body.expires_at),
        )
        audit_security_event(conn, "info", "api_key_created", "API key created", request, principal, {"api_key_id": item_id, "name": body.name, "prefix": prefix, "scopes": body.scopes, "expires_at": body.expires_at})
    return ok({"id": item_id, "name": body.name, "key": raw, "prefix": prefix, "scopes": body.scopes})


@router.patch("/api-keys/{key_id}")
def patch_key(key_id: str, payload: dict[str, Any], request: Request, principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        if "enabled" in payload:
            conn.execute("UPDATE api_keys SET enabled=? WHERE id=?", (1 if payload["enabled"] else 0, key_id))
        audit_security_event(conn, "info", "api_key_updated", "API key updated", request, principal, {"api_key_id": key_id, "changed_fields": field_names(payload), "enabled": payload.get("enabled")})
    return ok({"id": key_id})


@router.delete("/api-keys/{key_id}")
def delete_key(key_id: str, request: Request, principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
        audit_security_event(conn, "warning", "api_key_deleted", "API key deleted", request, principal, {"api_key_id": key_id})
    return ok({"deleted": key_id})


@router.get("/cameras")
def list_cameras(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM cameras ORDER BY is_primary DESC, created_at")
    return ok(rows)


def ensure_camera_profiles(conn, camera_id: str) -> None:
    ts = now_iso()
    existing = {
        row["mode"]
        for row in conn.execute(
            "SELECT mode FROM camera_profiles WHERE camera_id=? AND mode IN ('daytime', 'nighttime')",
            (camera_id,),
        ).fetchall()
    }
    for mode in ("daytime", "nighttime"):
        if mode in existing:
            continue
        conn.execute(
            "INSERT INTO camera_profiles (id, camera_id, name, mode, settings, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_id(), camera_id, mode.title(), mode, json_dumps(default_profile(mode)), ts, ts),
        )


def ensure_all_camera_profiles(conn) -> None:
    for row in conn.execute("SELECT id FROM cameras").fetchall():
        ensure_camera_profiles(conn, row["id"])


@router.post("/cameras/detect")
async def detect_cameras(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    found = []
    seen = set()
    for adapter in adapters().values():
        for cam in await adapter.detect():
            key = (cam.backend, cam.id)
            if key in seen:
                continue
            seen.add(key)
            found.append(cam.__dict__)
    return ok(found)


@router.post("/cameras")
def create_camera(body: CameraCreate, request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    camera_id = new_id()
    with session() as conn:
        if body.is_primary:
            conn.execute("UPDATE cameras SET is_primary=0")
        conn.execute(
            """INSERT INTO cameras (id, name, adapter, device_id, model, serial, enabled, is_primary, capabilities, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)""",
            (camera_id, body.name, body.adapter, body.device_id, body.model, body.serial, int(body.enabled), int(body.is_primary), now_iso(), now_iso()),
        )
        ensure_camera_profiles(conn, camera_id)
        audit_security_event(
            conn,
            "info",
            "camera_created",
            "Camera created",
            request,
            principal,
            {"camera_id": camera_id, "name": body.name, "adapter": body.adapter, "model": body.model, "enabled": body.enabled, "is_primary": body.is_primary},
        )
    return ok({"id": camera_id})


@router.get("/cameras/{camera_id}")
def get_camera(camera_id: str, _principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone()))
    if not row:
        raise HTTPException(404, "Camera not found")
    return ok(row)


@router.patch("/cameras/{camera_id}")
def patch_camera(camera_id: str, body: CameraPatch, request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    values = body.model_dump(exclude_unset=True)
    if not values:
        return ok({"id": camera_id})
    with session() as conn:
        if values.get("is_primary"):
            conn.execute("UPDATE cameras SET is_primary=0")
        for key in ["enabled", "is_primary"]:
            if key in values:
                values[key] = int(values[key])
        assignments = ", ".join(f"{k}=?" for k in values)
        conn.execute(f"UPDATE cameras SET {assignments}, updated_at=? WHERE id=?", (*values.values(), now_iso(), camera_id))
        audit_security_event(conn, "info", "camera_updated", "Camera updated", request, principal, {"camera_id": camera_id, "changed_fields": field_names(values), "is_primary": body.is_primary, "enabled": body.enabled})
    return ok({"id": camera_id})


@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str, request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    with session() as conn:
        conn.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
        audit_security_event(conn, "warning", "camera_deleted", "Camera deleted", request, principal, {"camera_id": camera_id})
    return ok({"deleted": camera_id})


@router.get("/cameras/{camera_id}/capabilities")
async def camera_capabilities(camera_id: str, _principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        cam = get_primary_camera(conn, camera_id)
    adapter = get_adapter(cam["adapter"])
    if hasattr(adapter, "get_capabilities_for_device"):
        caps = await adapter.get_capabilities_for_device(cam.get("device_id"))
    else:
        caps = await adapter.get_capabilities()
    return ok(caps.__dict__)


@router.get("/cameras/{camera_id}/settings-schema")
async def camera_settings_schema(camera_id: str, _principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        cam = get_primary_camera(conn, camera_id)
    return ok(await get_adapter(cam["adapter"]).get_settings_schema())


@router.post("/cameras/{camera_id}/test")
async def camera_test(camera_id: str, body: CaptureBody | None = None, principal: dict = Depends(require_scope("write:capture"))):
    payload = body or CaptureBody(camera_id=camera_id)
    payload.camera_id = camera_id
    return await capture_image(payload, principal, job_type="test")


@router.get("/settings")
def get_settings_rows(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM system_settings ORDER BY key")
    return ok({row["key"]: row["value"] for row in rows})


@router.patch("/settings")
def patch_settings(body: SettingsPatch, request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    with session() as conn:
        for key, value in body.values.items():
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)", (key, json_dumps(value), now_iso()))
        audit_security_event(conn, "info", "settings_updated", "Settings updated", request, principal, {"settings_keys": settings_keys(body.values)})
    return ok(body.values)


@router.get("/camera-profiles")
def camera_profiles(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        ensure_all_camera_profiles(conn)
        rows = all_rows(conn, "SELECT * FROM camera_profiles ORDER BY mode, name")
    return ok(rows)


@router.post("/camera-profiles")
def create_profile(payload: dict[str, Any], request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    profile_id = new_id()
    with session() as conn:
        conn.execute(
            "INSERT INTO camera_profiles (id, camera_id, name, mode, settings, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (profile_id, payload["camera_id"], payload["name"], payload.get("mode", "custom"), json_dumps(payload.get("settings", {})), now_iso(), now_iso()),
        )
        audit_security_event(
            conn,
            "info",
            "camera_profile_created",
            "Camera profile created",
            request,
            principal,
            {"profile_id": profile_id, "camera_id": payload["camera_id"], "mode": payload.get("mode", "custom"), "settings_keys": profile_settings_keys(payload)},
        )
    return ok({"id": profile_id})


@router.get("/camera-profiles/{profile_id}")
def get_profile(profile_id: str, _principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM camera_profiles WHERE id=?", (profile_id,)).fetchone()))
    if not row:
        raise HTTPException(404, "Profile not found")
    return ok(row)


@router.patch("/camera-profiles/{profile_id}")
def patch_profile(profile_id: str, payload: dict[str, Any], request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    with session() as conn:
        if "settings" in payload:
            conn.execute("UPDATE camera_profiles SET settings=?, updated_at=? WHERE id=?", (json_dumps(payload["settings"]), now_iso(), profile_id))
        audit_security_event(conn, "info", "camera_profile_updated", "Camera profile updated", request, principal, {"profile_id": profile_id, "changed_fields": field_names(payload), "settings_keys": profile_settings_keys(payload)})
    return ok({"id": profile_id})


@router.delete("/camera-profiles/{profile_id}")
def delete_profile(profile_id: str, request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    with session() as conn:
        conn.execute("DELETE FROM camera_profiles WHERE id=?", (profile_id,))
        audit_security_event(conn, "warning", "camera_profile_deleted", "Camera profile deleted", request, principal, {"profile_id": profile_id})
    return ok({"deleted": profile_id})


@router.get("/capture/state")
def capture_state(_principal: Annotated[dict, Depends(require_scope("read:status"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM capture_state WHERE id=1").fetchone()))
    return ok(row)


@router.post("/capture/start")
def capture_start(_principal: Annotated[dict, Depends(require_scope("write:capture"))]):
    with session() as conn:
        conn.execute(
            "UPDATE capture_state SET status='running', current_mode='automation', last_error=NULL, started_at=COALESCE(started_at, ?), updated_at=? WHERE id=1",
            (now_iso(), now_iso()),
        )
        event(conn, "capture_started", {})
    return ok({"status": "running"})


@router.post("/capture/stop")
def capture_stop(_principal: Annotated[dict, Depends(require_scope("write:capture"))]):
    with session() as conn:
        ts = now_iso()
        running = all_rows(conn, "SELECT id, type FROM capture_jobs WHERE status='running' AND type IN ('test', 'single', 'scheduled', 'sequence', 'sequence_item') ORDER BY started_at")
        conn.execute("UPDATE capture_state SET status='stopped', current_mode='manual', updated_at=? WHERE id=1", (ts,))
        cur = conn.execute(
            "UPDATE capture_jobs SET status='canceled', completed_at=?, error='Canceled by operator stop' WHERE status IN ('pending', 'claimed') AND type IN ('test', 'single', 'scheduled', 'sequence')",
            (ts,),
        )
        cancel_requested = conn.execute(
            "UPDATE capture_jobs SET cancel_requested_at=?, cancel_reason='Operator stop', cancel_mode='best_effort' WHERE status='running' AND type IN ('test', 'single', 'scheduled', 'sequence', 'sequence_item')",
            (ts,),
        )
        payload = {
            "status": "stopped",
            "stop_mode": "graceful",
            "canceled_jobs": cur.rowcount,
            "in_progress_jobs": len(running),
            "in_progress_job_ids": [job["id"] for job in running],
            "adapter_cancel_mode": "best_effort",
            "cancel_requested_jobs": cancel_requested.rowcount,
            "cancel_requested_job_ids": [job["id"] for job in running],
            "message": "Queued capture jobs were canceled. Running exposures were asked to stop; adapters with safe hard-cancel support will interrupt them, otherwise they finish gracefully.",
        }
        event(conn, "capture_stopped", payload)
    return ok(payload)


@router.post("/capture/pause")
def capture_pause(_principal: Annotated[dict, Depends(require_scope("write:capture"))]):
    with session() as conn:
        conn.execute("UPDATE capture_state SET status='paused', current_mode='paused', updated_at=? WHERE id=1", (now_iso(),))
        event(conn, "capture_paused", {})
    return ok({"status": "paused"})


@router.post("/capture/resume")
def capture_resume(_principal: Annotated[dict, Depends(require_scope("write:capture"))]):
    with session() as conn:
        conn.execute(
            "UPDATE capture_state SET status='running', current_mode='automation', last_error=NULL, started_at=COALESCE(started_at, ?), updated_at=? WHERE id=1",
            (now_iso(), now_iso()),
        )
        event(conn, "capture_resumed", {})
    return ok({"status": "running"})


@router.post("/capture/test-shot")
def test_shot(body: CaptureBody, _principal: dict = Depends(require_scope("write:capture"))):
    return ok(enqueue_capture(CaptureCommand.from_mapping(body.model_dump()), "test"))


@router.post("/capture/single")
def single_capture(body: CaptureBody, _principal: dict = Depends(require_scope("write:capture"))):
    return ok(enqueue_capture(CaptureCommand.from_mapping(body.model_dump()), "single"))


@router.post("/capture/sequence")
def capture_sequence(body: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("write:capture"))]):
    with session() as conn:
        job_id = create_capture_job(conn, "sequence", body)
    return ok({"id": job_id, "status": "pending", "type": "sequence", "request": body, "progress": 0})


@router.get("/capture/jobs")
def capture_jobs(_principal: Annotated[dict, Depends(require_scope("read:status"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM capture_jobs ORDER BY created_at DESC LIMIT 100")
    return ok(rows)


@router.get("/capture/jobs/{job_id}")
def capture_job(job_id: str, _principal: Annotated[dict, Depends(require_scope("read:status"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM capture_jobs WHERE id=?", (job_id,)).fetchone()))
    if not row:
        raise HTTPException(404, "Job not found")
    return ok(row)


@router.get("/schedule")
def get_schedule(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM capture_schedule LIMIT 1").fetchone()))
    return ok(row)


@router.put("/schedule")
def put_schedule(body: SchedulePut, request: Request, principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    start_sun_angle = body.start_sun_angle if body.start_sun_angle is not None else body.sun_angle
    end_sun_angle = body.end_sun_angle if body.end_sun_angle is not None else body.sun_angle
    with session() as conn:
        row = conn.execute("SELECT id FROM capture_schedule LIMIT 1").fetchone()
        schedule_id = row["id"] if row else new_id()
        conn.execute(
            """INSERT OR REPLACE INTO capture_schedule
               (id, enabled, start_mode, end_mode, sun_angle, start_sun_angle, end_sun_angle, fixed_start_time, fixed_end_time, timezone, latitude, longitude,
                interval_seconds, exposure_ramping_enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM capture_schedule WHERE id=?), ?), ?)""",
            (schedule_id, int(body.enabled), body.start_mode, body.end_mode, body.sun_angle, start_sun_angle, end_sun_angle, body.fixed_start_time, body.fixed_end_time,
             body.timezone, body.latitude, body.longitude, body.interval_seconds, int(body.exposure_ramping_enabled), schedule_id, now_iso(), now_iso()),
        )
        event(conn, "schedule_updated", {"id": schedule_id})
        audit_security_event(
            conn,
            "info",
            "schedule_updated",
            "Schedule updated",
            request,
            principal,
            {"schedule_id": schedule_id, "changed_fields": field_names(body.model_dump()), "enabled": body.enabled, "timezone": body.timezone},
        )
    payload = body.model_dump()
    payload["start_sun_angle"] = start_sun_angle
    payload["end_sun_angle"] = end_sun_angle
    return ok({"id": schedule_id, **payload})


@router.post("/schedule/preview-tonight")
def preview_tonight(payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    schedule = {**current_schedule(), **payload}
    preview_now = None
    if isinstance(schedule.get("now"), str):
        preview_now = datetime.fromisoformat(schedule.pop("now"))
    preview = active_window(schedule, preview_now)
    mode = "night" if preview["active"] else "day"
    try:
        preview = {**preview, **scheduled_capture_timing(mode, preview_now)}
    except LookupError:
        preview = {
            **preview,
            "capture_mode": mode,
            "capture_enabled": False,
            "save_enabled": False,
            "interval_seconds": None,
            "last_scheduled_capture_at": None,
            "last_scheduled_capture_started_at": None,
            "next_capture_due_at": None,
            "capture_due": False,
            "seconds_until_due": None,
        }
    return ok(preview)


@router.post("/schedule/recalculate")
def recalculate(_principal: Annotated[dict, Depends(require_scope("write:settings"))]):
    return ok({"status": "queued"})


@router.get("/images")
def images(limit: int = Query(50, le=500), offset: int = 0, day_key: str | None = None, mode: str | None = None, _principal: dict = Depends(require_scope("read:images"))):
    clauses: list[str] = []
    params: list[Any] = []
    if day_key:
        clauses.append("day_key=?")
        params.append(day_key)
    if mode:
        clauses.append("mode=?")
        params.append(mode)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with session() as conn:
        rows = all_rows(conn, f"SELECT * FROM images {where} ORDER BY captured_at DESC LIMIT ? OFFSET ?", (*params, limit, offset))
    return ok(rows, extra_meta={"limit": limit, "offset": offset})


@router.get("/images/latest")
def latest_image(_principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()))
    return ok(row)


@router.post("/images/retention/run")
def run_image_retention(
    _principal: Annotated[dict, Depends(require_scope("write:processing"))],
    days: int | None = Query(default=None, ge=0, le=3650),
):
    with session() as conn:
        retention_days = configured_image_retention_days(conn) if days is None else days
        result = cleanup_images_by_retention(conn, retention_days)
        event(conn, "image_retention_cleanup", {"retention_days": retention_days, "deleted_images": result["deleted_images"]})
    return ok(result)


def public_page_enabled() -> bool:
    with session() as conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key='public_page'").fetchone()
    if not row:
        return True
    value = json_loads(row["value"], {})
    if not isinstance(value, dict):
        return True
    return bool(value.get("enabled", True))


def require_public_page_enabled() -> None:
    if not public_page_enabled():
        raise HTTPException(403, "Public page is disabled")


@router.get("/public/latest")
def public_latest_image():
    require_public_page_enabled()
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()))
    latest_payload = read_latest_payload()
    if not row and not latest_payload:
        raise HTTPException(404, "No latest image is available")
    if latest_payload and (not row or latest_payload.get("id") != row.get("id")):
        latest_payload.pop("metadata", None)
        return ok(latest_payload)
    settings = get_settings()
    latest_image = settings.latest_dir / f"latest.{row['format'].lower()}"
    latest_thumbnail = next(settings.latest_dir.glob("latest-thumbnail.*"), None)
    return ok(public_latest_payload(row, latest_image if latest_image.exists() else None, latest_thumbnail if latest_thumbnail and latest_thumbnail.exists() else None))


@router.get("/public/latest/download")
def public_latest_download():
    require_public_page_enabled()
    with session() as conn:
        row = conn.execute("SELECT format FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()
    latest_payload = read_latest_payload()
    latest_file_name = latest_payload.get("latest_file") if latest_payload else None
    if latest_file_name:
        latest_image = get_settings().latest_dir / Path(str(latest_file_name)).name
    elif row:
        latest_image = get_settings().latest_dir / f"latest.{row['format'].lower()}"
    else:
        raise HTTPException(404, "No latest image is available")
    if not latest_image.exists():
        raise HTTPException(404, "Latest image file not found")
    return FileResponse(latest_image)


@router.get("/public/latest/thumbnail")
def public_latest_thumbnail():
    require_public_page_enabled()
    latest_thumbnail = next(get_settings().latest_dir.glob("latest-thumbnail.*"), None)
    if not latest_thumbnail or not latest_thumbnail.exists():
        raise HTTPException(404, "Latest thumbnail file not found")
    return FileResponse(latest_thumbnail)


@router.get("/images/days")
def image_days(_principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        rows = [dict(row) for row in conn.execute("SELECT day_key, COUNT(*) AS count FROM images GROUP BY day_key ORDER BY day_key DESC")]
    return ok(rows)


@router.get("/images/day/{day_key}")
def images_for_day(day_key: str, _principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM images WHERE day_key=? ORDER BY captured_at", (day_key,))
    return ok(rows)


@router.get("/images/{image_id}")
def image_detail(image_id: str, _principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()))
    if not row:
        raise HTTPException(404, "Image not found")
    return ok(row)


@router.get("/images/{image_id}/download")
def image_download(image_id: str):
    with session() as conn:
        row = conn.execute("SELECT file_path FROM images WHERE id=?", (image_id,)).fetchone()
    if not row or not Path(row["file_path"]).exists():
        raise HTTPException(404, "Image file not found")
    return FileResponse(row["file_path"])


def republish_latest_from_database(conn) -> dict[str, Any] | None:
    row = decode_row(row_to_dict(conn.execute("SELECT * FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()))
    if not row or not row.get("file_path") or not Path(row["file_path"]).exists():
        return None
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    thumbnail = Path(row["thumbnail_path"]) if row.get("thumbnail_path") and Path(row["thumbnail_path"]).exists() else None
    return publish_latest_image(row, metadata, thumbnail)


@router.delete("/images/{image_id}")
def delete_image(image_id: str, _principal: Annotated[dict, Depends(require_scope("write:processing"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()))
        if not row:
            raise HTTPException(404, "Image not found")
        file_result = delete_image_files(row)
        conn.execute("DELETE FROM images WHERE id=?", (image_id,))
        republished_latest = republish_latest_from_database(conn) if any(Path(path).name == "latest.json" for path in file_result["deleted_files"]) else None
        event(conn, "image_deleted", {"image_id": image_id, "deleted_files": len(file_result["deleted_files"]), "skipped_files": len(file_result["skipped_files"])})
    return ok({"deleted": image_id, **file_result, "latest_republished": republished_latest})


@router.post("/images/{image_id}/reprocess")
def reprocess_image(image_id: str, _principal: Annotated[dict, Depends(require_scope("write:processing"))]):
    with session() as conn:
        job_id = new_id()
        conn.execute("INSERT INTO processing_jobs (id, type, status, input, created_at) VALUES (?, 'thumbnail', 'pending', ?, ?)", (job_id, json_dumps({"image_id": image_id}), now_iso()))
    return ok({"id": job_id, "status": "pending"})


@router.get("/processing/jobs")
def processing_jobs(_principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM processing_jobs ORDER BY created_at DESC LIMIT 100")
    return ok(rows)


@router.get("/processing/jobs/{job_id}")
def processing_job(job_id: str, _principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM processing_jobs WHERE id=?", (job_id,)).fetchone()))
    if not row:
        raise HTTPException(404, "Processing job not found")
    return ok(row)


@router.get("/products")
def products(_principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM night_products ORDER BY created_at DESC")
    return ok(rows)


@router.post("/products/retention/run")
def run_product_retention(
    _principal: Annotated[dict, Depends(require_scope("write:processing"))],
    days: int | None = Query(default=None, ge=0, le=3650),
):
    with session() as conn:
        retention_days = configured_image_retention_days(conn) if days is None else days
        result = cleanup_products_by_retention(conn, retention_days)
        event(conn, "product_retention_cleanup", {"retention_days": retention_days, "deleted_products": result["deleted_products"]})
    return ok(result)


@router.get("/products/{product_id}")
def product(product_id: str, _principal: Annotated[dict, Depends(require_scope("read:images"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM night_products WHERE id=?", (product_id,)).fetchone()))
    if not row:
        raise HTTPException(404, "Product not found")
    return ok(row)


@router.post("/products/{product_type}")
def create_product(product_type: str, payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("write:processing"))]):
    if product_type not in {"keogram", "startrail", "timelapse", "mini-timelapse"}:
        raise HTTPException(404, "Unknown product type")
    job_type = product_type.replace("-", "_")
    with session() as conn:
        job_id = new_id()
        conn.execute("INSERT INTO processing_jobs (id, type, status, input, created_at) VALUES (?, ?, 'pending', ?, ?)", (job_id, job_type, json_dumps(payload), now_iso()))
    return ok({"id": job_id, "type": job_type, "status": "pending", "input": payload, "progress": 0})


@router.delete("/products/{product_id}")
def delete_product(product_id: str, _principal: Annotated[dict, Depends(require_scope("write:processing"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM night_products WHERE id=?", (product_id,)).fetchone()))
        if not row:
            raise HTTPException(404, "Product not found")
        file_result = delete_product_files(row)
        conn.execute("DELETE FROM night_products WHERE id=?", (product_id,))
        event(conn, "product_deleted", {"product_id": product_id, "deleted_files": len(file_result["deleted_files"]), "skipped_files": len(file_result["skipped_files"])})
    return ok({"deleted": product_id, **file_result})


@router.get("/products/{product_id}/download")
def product_download(product_id: str):
    with session() as conn:
        row = conn.execute("SELECT file_path FROM night_products WHERE id=?", (product_id,)).fetchone()
    if not row or not row["file_path"] or not Path(row["file_path"]).exists():
        raise HTTPException(404, "Product file not found")
    return FileResponse(row["file_path"])


@router.get("/dark-frames")
def dark_frames(_principal: Annotated[dict, Depends(require_scope("read:images"))]):
    return ok([])


@router.post("/dark-frames/capture")
def capture_dark_frame(_principal: Annotated[dict, Depends(require_scope("write:capture"))]):
    return ok({"status": "planned", "note": "Dark-frame capture will run through the capture daemon."})


@router.delete("/dark-frames/{frame_id}")
def delete_dark_frame(frame_id: str, _principal: Annotated[dict, Depends(require_scope("write:processing"))]):
    return ok({"deleted": frame_id})


@router.get("/modules")
def modules(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM plugin_modules ORDER BY name")
    return ok(rows)


@router.post("/modules/upload")
def upload_module(_principal: Annotated[dict, Depends(require_scope("admin"))]):
    return ok({"status": "disabled", "note": "Custom module uploads are disabled until sandboxing and signing are implemented."})


@router.patch("/modules/{module_id}")
def patch_module(module_id: str, payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("admin"))]):
    allowed = {key: payload[key] for key in ("enabled", "settings") if key in payload}
    if not allowed:
        raise HTTPException(400, "No supported module fields provided")
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM plugin_modules WHERE id=?", (module_id,)).fetchone()))
        if not row:
            raise HTTPException(404, "Module not found")
        if row.get("module_path"):
            raise HTTPException(403, "Uploaded custom modules cannot be changed until sandboxing and signing are implemented")
        enabled = int(bool(allowed.get("enabled", row.get("enabled"))))
        settings = allowed.get("settings", row.get("settings") or {})
        if not isinstance(settings, dict):
            raise HTTPException(400, "Module settings must be an object")
        conn.execute("UPDATE plugin_modules SET enabled=?, settings=?, updated_at=? WHERE id=?", (enabled, json_dumps(settings), now_iso(), module_id))
        event(conn, "module_updated", {"module_id": module_id, "enabled": bool(enabled), "settings_keys": sorted(settings.keys())})
        updated = decode_row(row_to_dict(conn.execute("SELECT * FROM plugin_modules WHERE id=?", (module_id,)).fetchone()))
    return ok(updated)


@router.delete("/modules/{module_id}")
def delete_module(module_id: str, _principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM plugin_modules WHERE id=?", (module_id,)).fetchone()))
        if not row:
            raise HTTPException(404, "Module not found")
        if row.get("trusted") or row.get("module_path") is None:
            raise HTTPException(403, "Built-in modules cannot be deleted")
        conn.execute("DELETE FROM plugin_modules WHERE id=?", (module_id,))
    return ok({"deleted": module_id})


@router.get("/module-flows")
def module_flows(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT * FROM module_flows ORDER BY name")
    return ok(rows)


@router.patch("/module-flows/{flow_id}")
def patch_flow(flow_id: str, payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("admin"))]):
    return ok({"id": flow_id, "payload": payload})


@router.post("/module-flows/{flow_id}/run")
def run_flow(flow_id: str, _principal: Annotated[dict, Depends(require_scope("write:processing"))]):
    return ok({"id": flow_id, "status": "queued"})


@router.get("/remote-targets")
def remote_targets(_principal: Annotated[dict, Depends(require_scope("read:settings"))]):
    with session() as conn:
        rows = all_rows(conn, "SELECT id, name, type, enabled, created_at, updated_at FROM remote_targets")
    return ok(rows)


@router.post("/remote-targets")
def create_remote_target(payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("admin"))]):
    target_id = new_id()
    with session() as conn:
        conn.execute("INSERT INTO remote_targets (id, name, type, config_encrypted, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (target_id, payload["name"], payload["type"], json_dumps({"redacted": True}), int(payload.get("enabled", False)), now_iso(), now_iso()))
    return ok({"id": target_id})


@router.patch("/remote-targets/{target_id}")
def patch_remote_target(target_id: str, payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("admin"))]):
    return ok({"id": target_id, "payload": {k: "***" if "password" in k else v for k, v in payload.items()}})


@router.delete("/remote-targets/{target_id}")
def delete_remote_target(target_id: str, _principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        conn.execute("DELETE FROM remote_targets WHERE id=?", (target_id,))
    return ok({"deleted": target_id})


@router.post("/remote-targets/{target_id}/test")
def test_remote_target(target_id: str, _principal: Annotated[dict, Depends(require_scope("admin"))]):
    return ok({"id": target_id, "status": "planned"})


@router.post("/uploads/retry")
def retry_uploads(_principal: Annotated[dict, Depends(require_scope("write:processing"))]):
    return ok({"status": "queued"})


@router.get("/migration/allsky/detect")
def detect_allsky(_principal: Annotated[dict, Depends(require_scope("admin"))]):
    home = Path.home()
    candidates = [home / "allsky", home / "allsky-OLD", home / "allsky-SAVED", Path("/home/pi/allsky"), Path("/var/www/html/allsky")]
    found = [{"path": str(p), "exists": p.exists()} for p in candidates]
    return ok(found)


@router.post("/migration/allsky/preview")
def preview_allsky(payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("admin"))]):
    root = Path(payload.get("path", ""))
    counts = {
        "images": count_files(root, ["*.jpg", "*.jpeg", "*.png"]),
        "timelapses": count_files(root, ["*.mp4", "*.webm"]),
        "keograms": count_files(root, ["*keogram*.jpg", "*keogram*.png"]),
        "startrails": count_files(root, ["*startrail*.jpg", "*startrail*.png"]),
    }
    return ok({"path": str(root), "exists": root.exists(), "counts": counts, "will_delete_original": False})


@router.post("/migration/allsky/import")
def import_allsky(payload: dict[str, Any], _principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        job_id = new_id()
        conn.execute("INSERT INTO processing_jobs (id, type, status, input, created_at) VALUES (?, 'allsky_import', 'pending', ?, ?)", (job_id, json_dumps(payload), now_iso()))
    return ok({"id": job_id, "status": "pending", "will_delete_original": False})


@router.get("/migration/jobs/{job_id}")
def migration_job(job_id: str, _principal: Annotated[dict, Depends(require_scope("admin"))]):
    with session() as conn:
        row = decode_row(row_to_dict(conn.execute("SELECT * FROM processing_jobs WHERE id=?", (job_id,)).fetchone()))
    if not row:
        raise HTTPException(404, "Migration job not found")
    return ok(row)


@router.get("/events/stream")
async def event_stream(_principal: Annotated[dict, Depends(require_scope("read:status"))]):
    async def stream():
        last_id = ""
        while True:
            with session() as conn:
                rows = all_rows(conn, "SELECT * FROM events WHERE id > ? ORDER BY created_at LIMIT 20", (last_id,))
            for row in rows:
                last_id = row["id"]
                yield f"event: {row['type']}\ndata: {json.dumps(row)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(stream(), media_type="text/event-stream")
