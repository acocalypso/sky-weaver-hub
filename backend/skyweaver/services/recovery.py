from typing import Any

from ..db import event, log, now_iso, session


def recover_capture_jobs() -> dict[str, Any]:
    """Requeue capture work that was interrupted by a daemon restart."""
    ts = now_iso()
    with session() as conn:
        rows = conn.execute(
            "SELECT id, type, status FROM capture_jobs WHERE status IN ('claimed', 'running') ORDER BY created_at"
        ).fetchall()
        if not rows:
            return {"requeued": 0, "jobs": []}
        jobs = [{"id": row["id"], "type": row["type"], "previous_status": row["status"]} for row in rows]
        conn.execute(
            """UPDATE capture_jobs
               SET status='pending', progress=0, result=NULL, error=NULL, started_at=NULL, completed_at=NULL
               WHERE status IN ('claimed', 'running')""",
        )
        conn.execute(
            "UPDATE capture_state SET daemon_last_claimed_job_id=NULL, daemon_last_claimed_job_type=NULL, daemon_last_claimed_at=NULL, updated_at=? WHERE id=1",
            (ts,),
        )
        log(conn, "warning", "capture-daemon", "Recovered interrupted capture jobs after service start", {"jobs": jobs})
        event(conn, "capture_jobs_recovered", {"jobs": jobs})
        return {"requeued": len(jobs), "jobs": jobs}


def recover_processing_jobs() -> dict[str, Any]:
    """Requeue processing work that was interrupted by a worker restart."""
    with session() as conn:
        rows = conn.execute(
            "SELECT id, type, status FROM processing_jobs WHERE status IN ('claimed', 'running') ORDER BY created_at"
        ).fetchall()
        if not rows:
            return {"requeued": 0, "jobs": []}
        jobs = [{"id": row["id"], "type": row["type"], "previous_status": row["status"]} for row in rows]
        conn.execute(
            """UPDATE processing_jobs
               SET status='pending', progress=0, output=NULL, error=NULL, started_at=NULL, completed_at=NULL
               WHERE status IN ('claimed', 'running')""",
        )
        log(conn, "warning", "worker", "Recovered interrupted processing jobs after service start", {"jobs": jobs})
        event(conn, "processing_jobs_recovered", {"jobs": jobs})
        return {"requeued": len(jobs), "jobs": jobs}


def recover_interrupted_jobs() -> dict[str, Any]:
    capture = recover_capture_jobs()
    processing = recover_processing_jobs()
    return {"capture": capture, "processing": processing, "total_requeued": capture["requeued"] + processing["requeued"]}
