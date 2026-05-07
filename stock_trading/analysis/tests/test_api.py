from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from analysis.models import ReviewReport
from trades.models import TradeRecord


@pytest.fixture
def api_client(db):
    user = get_user_model().objects.create_user(username="analysis-api", password="secret")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_generate_review_report_endpoint(api_client, monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("REVIEW_LLM_BASE_URL", "")
    monkeypatch.setenv("REVIEW_LLM_API_KEY", "")
    monkeypatch.setenv("REVIEW_LLM_MODEL", "")
    trade = TradeRecord.objects.create(
        stock_code="603063",
        stock_name="Test A",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("41.4300"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    response = api_client.post("/api/analysis/generate/", {"trade_record_id": trade.id}, format="json")

    assert response.status_code == 201
    payload = response.json()
    assert payload["trade_record"] == trade.id
    assert payload["overall_score"] >= 0
    assert payload["engine_version"] == "llm_review_v1"
    assert payload["report_kind"] == "llm_coach"
    assert "score" not in payload
    assert "suggestions" not in payload
    assert payload["subscores"]["decision_quality"] >= 0
    assert payload["coach_report_payload"]["follow_up_advice"]
    assert payload["coach_report_payload"]["next_time_rules"]
    assert "price_chart" in payload["trend_analysis"]
    assert "volume_chart" in payload["volume_analysis"]
    assert payload["intent_gap_diagnosis"]["gap_level"]
    assert ReviewReport.objects.filter(trade_record=trade).exists()


@pytest.mark.django_db
def test_generate_review_report_creates_version_history(api_client, monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("REVIEW_LLM_BASE_URL", "")
    monkeypatch.setenv("REVIEW_LLM_API_KEY", "")
    monkeypatch.setenv("REVIEW_LLM_MODEL", "")
    trade = TradeRecord.objects.create(
        stock_code="603063",
        stock_name="Test B",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("41.4300"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    first = api_client.post("/api/analysis/generate/", {"trade_record_id": trade.id}, format="json")
    second = api_client.post("/api/analysis/generate/", {"trade_record_id": trade.id}, format="json")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    list_response = api_client.get(f"/api/analysis/?trade_record={trade.id}")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 2
    assert payload[0]["is_latest"] is True
    assert payload[0]["version"] == 2
    assert payload[1]["is_latest"] is False
    assert payload[1]["version"] == 1


@pytest.mark.django_db
def test_generate_review_requires_trade_record_id(api_client):
    response = api_client.post("/api/analysis/generate/", {}, format="json")

    assert response.status_code == 400
    assert "trade_record_id" in str(response.json()["detail"])


@pytest.mark.django_db
def test_review_list_normalizes_fragmented_missing_data_notes(api_client):
    trade = TradeRecord.objects.create(
        stock_code="01712",
        stock_name="Dragon Test",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("8.2700"),
        quantity=1000,
        trade_time=timezone.now(),
        source=TradeRecord.Source.HSBC_EMAIL,
    )
    ReviewReport.objects.create(
        trade_record=trade,
        version=1,
        is_latest=True,
        coach_report_payload={
            "overall_verdict": "fallback",
            "missing_data_notes": [
                "i",
                "n",
                "t",
                "e",
                "n",
                "t",
                "_",
                "s",
                "n",
                "a",
                "p",
                "s",
                "h",
                "o",
                "t",
                "_",
                "m",
                "i",
                "s",
                "s",
                "i",
                "n",
                "g",
            ],
        },
    )

    response = api_client.get(f"/api/analysis/?trade_record={trade.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["coach_report_payload"]["missing_data_notes"] == ["intent_snapshot_missing"]
