from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from portfolio.models import Position
from portfolio.views import HKStockStatsViewSet, PositionViewSet
from trades.models import TradeRecord


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="tester", password="secret")


@pytest.mark.django_db
def test_active_positions_endpoint_returns_only_active_positions(user):
    Position.objects.create(
        stock_code="603063",
        stock_name="禾望电气",
        market=TradeRecord.Market.A_STOCK,
        quantity=100,
        cost_price=Decimal("41.4300"),
        weighted_avg_cost=Decimal("41.4300"),
        total_invested=Decimal("4143.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    Position.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        quantity=0,
        cost_price=Decimal("58.5000"),
        weighted_avg_cost=Decimal("58.5000"),
        total_invested=Decimal("0"),
        realized_pnl=Decimal("0"),
        status=Position.Status.CLEARED,
    )

    factory = APIRequestFactory()
    request = factory.get("/api/portfolio/positions/active/")
    force_authenticate(request, user=user)
    response = PositionViewSet.as_view({"get": "active"})(request)

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["stock_code"] == "603063"


@pytest.mark.django_db
def test_manual_entry_endpoint_creates_position(user):
    factory = APIRequestFactory()
    request = factory.post(
        "/api/portfolio/positions/manual_entry/",
        {
            "stock_code": "02610",
            "stock_name": "南山铝业国际",
            "market": TradeRecord.Market.HK_STOCK,
            "quantity": 100,
            "cost_price": "58.50",
            "entry_time": timezone.now().isoformat(),
        },
        format="json",
    )
    force_authenticate(request, user=user)

    response = PositionViewSet.as_view({"post": "manual_entry"})(request)

    assert response.status_code == 201
    assert response.data["stock_code"] == "02610"
    assert Position.objects.filter(stock_code="02610").exists()


@pytest.mark.django_db
def test_manual_entry_endpoint_returns_validation_error_for_bad_code(user):
    factory = APIRequestFactory()
    request = factory.post(
        "/api/portfolio/positions/manual_entry/",
        {
            "stock_code": "BAD",
            "stock_name": "Invalid",
            "market": TradeRecord.Market.A_STOCK,
            "quantity": 100,
            "cost_price": "10",
            "entry_time": timezone.now().isoformat(),
        },
        format="json",
    )
    force_authenticate(request, user=user)

    response = PositionViewSet.as_view({"post": "manual_entry"})(request)

    assert response.status_code == 400
    assert "Invalid A-stock code" in str(response.data["detail"])


@pytest.mark.django_db
def test_hk_stats_retrieve_endpoint_returns_summary(user):
    factory = APIRequestFactory()
    expected = {
        "stock_code": "02610",
        "stock_name": "南山铝业国际",
        "weighted_avg_cost": Decimal("58.5000"),
        "quantity": 100,
        "market_value": Decimal("6000.0000"),
        "unrealized_pnl": Decimal("150.0000"),
        "unrealized_pnl_pct": Decimal("2.5641"),
        "realized_pnl": Decimal("25.0000"),
        "daily_pnl": Decimal("100.0000"),
    }
    with patch("portfolio.views.CostCalculator.get_hk_stock_stats", return_value=expected):
        request = factory.get("/api/portfolio/hk-stats/02610/")
        force_authenticate(request, user=user)
        response = HKStockStatsViewSet.as_view({"get": "retrieve"})(request, pk="02610")

    assert response.status_code == 200
    assert response.data["stock_code"] == "02610"
    assert response.data["quantity"] == 100


@pytest.mark.django_db
def test_hk_trade_history_endpoint_returns_trade_records(user):
    trade = TradeRecord.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("58.5000"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.HSBC_EMAIL,
    )

    factory = APIRequestFactory()
    request = factory.get("/api/portfolio/hk-stats/02610/trade_history/")
    force_authenticate(request, user=user)
    response = HKStockStatsViewSet.as_view({"get": "trade_history"})(request, pk="02610")

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == trade.id
