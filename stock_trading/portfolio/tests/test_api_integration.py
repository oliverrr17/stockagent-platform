from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from portfolio.models import PortfolioPerformanceSnapshot, Position, PositionDailyContributionSnapshot
from trades.models import TradeRecord


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="api-user", password="secret")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_active_positions_endpoint_via_url(api_client):
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

    response = api_client.get("/api/portfolio/positions/active/")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["stock_code"] == "603063"


@pytest.mark.django_db
def test_manual_entry_endpoint_via_url(api_client):
    response = api_client.post(
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

    assert response.status_code == 201
    assert response.json()["stock_code"] == "02610"
    assert Position.objects.filter(stock_code="02610", status=Position.Status.ACTIVE).exists()


@pytest.mark.django_db
def test_hk_trade_history_endpoint_via_url(api_client):
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

    response = api_client.get("/api/portfolio/hk-stats/02610/trade_history/")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == trade.id


@pytest.mark.django_db
def test_hk_stats_endpoint_via_url(api_client):
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
        response = api_client.get("/api/portfolio/hk-stats/02610/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_code"] == "02610"
    assert payload["quantity"] == 100


@pytest.mark.django_db
def test_position_partial_update_via_url(api_client):
    position = Position.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        quantity=100,
        cost_price=Decimal("58.5000"),
        weighted_avg_cost=Decimal("58.5000"),
        total_invested=Decimal("5850.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )

    response = api_client.patch(
        f"/api/portfolio/positions/{position.id}/",
        {
            "stock_name": "南山铝业国际-修订",
            "quantity": 120,
            "cost_price": "59.2500",
        },
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_name"] == "南山铝业国际-修订"
    assert payload["quantity"] == 120


@pytest.mark.django_db
def test_position_delete_via_url_rejects_synced_positions(api_client):
    position = Position.objects.create(
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

    response = api_client.delete(f"/api/portfolio/positions/{position.id}/")

    assert response.status_code == 400
    assert "manually initialized" in response.json()["detail"]


@pytest.mark.django_db
def test_portfolio_analytics_overview_endpoint_via_url(api_client):
    response = api_client.get("/api/portfolio/analytics/overview/")

    assert response.status_code == 200
    payload = response.json()
    assert "total_assets_cny" in payload
    assert "returns" in payload
    assert "curves" in payload


@pytest.mark.django_db
def test_portfolio_dashboard_endpoint_via_url(api_client):
    response = api_client.get("/api/portfolio/analytics/dashboard/")

    assert response.status_code == 200
    payload = response.json()
    assert "positions" in payload
    assert "position_analytics" in payload
    assert "overview" in payload
    assert "cash_accounts" in payload
    assert "cash_flows" in payload


@pytest.mark.django_db
def test_portfolio_daily_contributions_endpoint_via_url(api_client):
    snapshot = PortfolioPerformanceSnapshot.objects.create(
        snapshot_date=timezone.localdate(),
        total_assets_cny=Decimal("100000.0000"),
        total_return_cny=Decimal("1200.0000"),
        daily_return_pct=Decimal("1.2000"),
        monthly_return_pct=Decimal("1.2000"),
        yearly_return_pct=Decimal("1.2000"),
        cumulative_return_pct=Decimal("1.2000"),
        audit_status="PROVISIONAL",
        external_flow_cny=Decimal("0.0000"),
        computed_daily_pnl_cny=Decimal("1200.0000"),
    )
    PositionDailyContributionSnapshot.objects.create(
        snapshot_date=snapshot.snapshot_date,
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        start_quantity=100,
        end_quantity=100,
        previous_close=Decimal("41.0000"),
        latest_price=Decimal("42.5000"),
        trade_cash_delta=Decimal("0.0000"),
        daily_pnl_native=Decimal("150.0000"),
        daily_pnl_cny=Decimal("150.0000"),
        fx_rate=Decimal("1.000000"),
        price_source="tushare_daily",
        source_trade_date=snapshot.snapshot_date,
        degraded=False,
        degraded_reason="",
        audit_status="FINAL",
    )

    response = api_client.get(f"/api/portfolio/analytics/contributions/{snapshot.snapshot_date.isoformat()}/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_date"] == snapshot.snapshot_date.isoformat()
    assert payload["audit_status"] == "PROVISIONAL"
    assert len(payload["contributions"]) == 1
    assert payload["contributions"][0]["stock_code"] == "603063"
