from pathlib import Path

from test_api import login, make_client


def test_recover_capture_jobs_requeues_interrupted_work(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    queued = client.post("/api/v1/capture/single", headers=headers, json={"mode": "manual"}).json()["data"]

    from skyweaver.db import session
    from skyweaver.services.recovery import recover_capture_jobs

    with session() as conn:
        conn.execute(
            "UPDATE capture_jobs SET status='running', progress=0.45, started_at='2026-06-23T00:00:00+00:00' WHERE id=?",
            (queued["id"],),
        )
        conn.execute(
            "UPDATE capture_state SET daemon_last_claimed_job_id=?, daemon_last_claimed_job_type='single', daemon_last_claimed_at='2026-06-23T00:00:00+00:00' WHERE id=1",
            (queued["id"],),
        )

    recovered = recover_capture_jobs()
    assert recovered["requeued"] == 1
    assert recovered["jobs"][0]["id"] == queued["id"]
    assert recovered["jobs"][0]["previous_status"] == "running"

    job = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert job["status"] == "pending"
    assert job["progress"] == 0
    assert job["started_at"] is None

    status = client.get("/api/v1/status", headers=headers).json()["data"]["capture"]
    assert status["daemon_last_claimed_job_id"] is None
    assert status["daemon_last_claimed_job_type"] is None
    assert status["daemon_last_claimed_at"] is None


def test_recover_processing_jobs_requeues_interrupted_work(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    queued = client.post("/api/v1/products/keogram", headers=headers, json={"day_key": "20260623"}).json()["data"]

    from skyweaver.db import session
    from skyweaver.services.recovery import recover_processing_jobs

    with session() as conn:
        conn.execute(
            "UPDATE processing_jobs SET status='running', progress=0.62, started_at='2026-06-23T00:00:00+00:00', error='interrupted' WHERE id=?",
            (queued["id"],),
        )

    recovered = recover_processing_jobs()
    assert recovered["requeued"] == 1
    assert recovered["jobs"][0]["id"] == queued["id"]
    assert recovered["jobs"][0]["previous_status"] == "running"

    job = client.get(f"/api/v1/processing/jobs/{queued['id']}", headers=headers).json()["data"]
    assert job["status"] == "pending"
    assert job["progress"] == 0
    assert job["started_at"] is None
    assert job["error"] is None
