from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def api_client(db):
    user = get_user_model().objects.create_user(username="ops-actions", password="secret")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_run_daily_action_returns_summary(api_client):
    with patch("stock_trading.config.status_views.execute_daily_ingestion", return_value={"ths_created_count": 1}):
        response = api_client.post("/api/status/actions/run-daily/", {}, format="json")

    assert response.status_code == 200
    assert response.json()["action"] == "run-daily"
    assert response.json()["ths_created_count"] == 1


@pytest.mark.django_db
def test_sync_positions_action_returns_validation_error(api_client):
    with patch(
        "stock_trading.config.status_views.execute_sync_ths_positions",
        side_effect=FileNotFoundError("bridge missing"),
    ):
        response = api_client.post("/api/status/actions/sync-ths-positions/", {}, format="json")

    assert response.status_code == 400
    assert "bridge missing" in response.json()["detail"]
