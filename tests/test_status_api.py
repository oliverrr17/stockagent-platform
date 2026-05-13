from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def api_client(db):
    user = get_user_model().objects.create_user(username="ops-api", password="secret")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_operations_status_endpoint_returns_counts_and_logs(api_client):
    scheduler_dir = Path(r"D:\stockagent\output\scheduler")
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    (scheduler_dir / "daily-ingestion-test.log").write_text(
        "[2026-04-22T18:30:00] Starting\n[2026-04-22T18:30:10] Finished\n",
        encoding="utf-8",
    )

    response = api_client.get("/api/status/operations/")

    assert response.status_code == 200
    payload = response.json()
    assert "counts" in payload
    assert "scheduler" in payload
    assert "alerts" in payload
    assert "recent_logs" in payload


@pytest.mark.django_db
def test_operations_status_endpoint_uses_hourly_news_fetch_defaults(api_client):
    with patch.dict(
        "os.environ",
        {
            "NEWS_FETCH_HOURS": "8,9,10,11,12,13,14,15,16,17,18,19,20,21,22",
            "NEWS_FETCH_MINUTE": "0",
        },
        clear=False,
    ):
        response = api_client.get("/api/status/operations/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scheduler"]["news_fetch"] == "8,9,10,11,12,13,14,15,16,17,18,19,20,21,22:00"


@pytest.mark.django_db
def test_operations_status_endpoint_includes_futu_scheduler_defaults(api_client):
    response = api_client.get("/api/status/operations/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scheduler"]["futu"] == "18:35"
