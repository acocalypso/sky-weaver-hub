from datetime import UTC, datetime, timedelta

import jwt
import pytest

from test_api import login, make_client


@pytest.mark.parametrize("role,can_capture,can_admin", [("admin", True, True), ("operator", True, False), ("viewer", False, False)])
def test_user_roles_enforce_permissions(tmp_path, role, can_capture, can_admin):
    client = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {login(client)}"}
    user = client.post("/api/v1/users", headers=admin, json={"username": "role-user", "password": "Role-user-secret-2026!"}).json()["data"]
    assert client.patch(f"/api/v1/users/{user['id']}", headers=admin, json={"role": role}).status_code == 200
    response = client.post("/api/v1/auth/login", json={"username": "role-user", "password": "Role-user-secret-2026!"})
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    principal = client.get("/api/v1/auth/me", headers=headers).json()["data"]
    assert principal["role"] == role
    assert ("admin" in principal["scopes"]) is can_admin
    assert client.get("/api/v1/status", headers=headers).status_code == 200
    assert client.get("/api/v1/users", headers=headers).status_code == (200 if can_admin else 403)
    assert client.post("/api/v1/capture/single", headers=headers, json={}).status_code == (200 if can_capture else 403)


def test_role_changes_and_user_deletion_apply_to_existing_tokens(tmp_path):
    client = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {login(client)}"}
    user_id = client.post("/api/v1/users", headers=admin, json={"username": "changing-user", "password": "Changing-user-2026!"}).json()["data"]["id"]
    client.patch(f"/api/v1/users/{user_id}", headers=admin, json={"role": "admin"})
    token = client.post("/api/v1/auth/login", json={"username": "changing-user", "password": "Changing-user-2026!"}).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/users", headers=headers).status_code == 200
    client.patch(f"/api/v1/users/{user_id}", headers=admin, json={"role": "viewer"})
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    assert client.get("/api/v1/auth/me", headers=headers).json()["data"]["role"] == "viewer"
    client.delete(f"/api/v1/users/{user_id}", headers=admin)
    assert client.get("/api/v1/status", headers=headers).status_code == 401


@pytest.mark.parametrize("expired", [True, False])
def test_api_key_expiration_is_enforced_before_recording_usage(tmp_path, expired):
    client = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {login(client)}"}
    expiration = datetime.now(UTC) + timedelta(days=-1 if expired else 1)
    response = client.post("/api/v1/api-keys", headers=admin, json={"name": "expiring", "scopes": ["read:status"], "expires_at": expiration.isoformat()})
    assert response.status_code == 200
    key = response.json()["data"]
    headers = {"Authorization": f"Bearer {key['key']}"}
    assert client.get("/api/v1/status", headers=headers).status_code == (401 if expired else 200)
    saved = next(row for row in client.get("/api/v1/api-keys", headers=admin).json()["data"] if row["id"] == key["id"])
    assert (saved["last_used_at"] is None) is expired


@pytest.mark.parametrize("expiration", ["garbage", "2026-12-01T00:00:00"])
def test_api_key_rejects_ambiguous_expiration_and_legacy_invalid_values(tmp_path, expiration):
    client = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {login(client)}"}
    assert client.post("/api/v1/api-keys", headers=admin, json={"name": "invalid", "expires_at": expiration}).status_code == 422
    key = client.post("/api/v1/api-keys", headers=admin, json={"name": "legacy"}).json()["data"]
    from skyweaver.db import session

    with session() as conn:
        conn.execute("UPDATE api_keys SET expires_at=? WHERE id=?", (expiration, key["id"]))
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {key['key']}"}).status_code == 401


@pytest.mark.parametrize("claims", [{}, {"sub": "missing-user"}, {"exp": 9999999999}])
def test_incomplete_signed_tokens_return_unauthorized(tmp_path, claims):
    client = make_client(tmp_path)
    from skyweaver.config import get_settings

    token = jwt.encode(claims, get_settings().secret_key, algorithm="HS256")
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_api_keys_cannot_change_user_passwords(tmp_path):
    client = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {login(client)}"}
    key = client.post("/api/v1/api-keys", headers=admin, json={"name": "admin-key", "scopes": ["admin"]}).json()["data"]["key"]
    response = client.patch("/api/v1/users/me/password", headers={"Authorization": f"Bearer {key}"}, json={"username": "admin", "password": "New-user-password-2026!"})
    assert response.status_code == 403
    assert login(client)


@pytest.mark.parametrize("password", ["Ab1!" * 18, "é" * 36])
def test_overlong_password_does_not_authenticate_as_its_72_byte_prefix(password):
    from skyweaver.security import hash_password, verify_password

    password_hash = hash_password(password)
    assert verify_password(password, password_hash)
    assert not verify_password(password + "extra", password_hash)
