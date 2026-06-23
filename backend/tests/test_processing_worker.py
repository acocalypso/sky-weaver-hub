import asyncio
from pathlib import Path

from test_api import login, make_client


def test_worker_generates_keogram_product(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    day_key = None
    for _ in range(3):
        res = client.post(
            "/api/v1/capture/test-shot",
            headers=headers,
            json={"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"},
        )
        assert res.status_code == 200, res.text
        day_key = res.json()["data"]["image"]["captured_at"][:10].replace("-", "")

    queued = client.post("/api/v1/products/keogram", headers=headers, json={"day_key": day_key}).json()["data"]
    assert queued["status"] == "pending"

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True

    products = client.get("/api/v1/products", headers=headers).json()["data"]
    assert len(products) == 1
    product = products[0]
    assert product["id"] == queued["id"]
    assert product["type"] == "keogram"
    assert product["status"] == "completed"
    assert product["metadata"]["source_images"] == 3
    assert Path(product["file_path"]).exists()

    download = client.get(f"/api/v1/products/{product['id']}/download")
    assert download.status_code == 200
