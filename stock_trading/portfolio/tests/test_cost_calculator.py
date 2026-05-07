import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from portfolio.models import Position
from portfolio.services.cost_calculator import CostCalculator
from trades.models import TradeRecord
from trades.services.trade_recorder import TradeRecorder


class FakeMarketAPI:
    def get_latest_price(self, stock_code: str, market: str):
        if stock_code == "02610":
            return Decimal("60.00")
        return Decimal("42.00")

    def get_previous_close(self, stock_code: str, market: str):
        if stock_code == "02610":
            return Decimal("59.00")
        return Decimal("41.00")


class BrokenSnapshotMarketAPI:
    def get_snapshot(self, stock_code: str, market: str):
        raise ConnectionError("market api unavailable")


class HKSnapshotMarketAPI:
    def get_snapshot(self, stock_code: str, market: str):
        return {
            "latest_price": Decimal("8.31"),
            "previous_close": Decimal("8.25"),
            "trade_date": "2026-04-24",
        }


@pytest.mark.django_db
def test_calculate_realized_pnl_uses_weighted_average_cost():
    position = Position.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        quantity=100,
        cost_price=Decimal("58.50"),
        weighted_avg_cost=Decimal("58.50"),
        total_invested=Decimal("5850"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    sell_trade = TradeRecord(
        stock_code=position.stock_code,
        stock_name=position.stock_name,
        market=position.market,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("60.00"),
        quantity=40,
        trade_time=timezone.now(),
        source=TradeRecord.Source.HSBC_EMAIL,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
    )

    realized_pnl = CostCalculator().calculate_realized_pnl("02610", sell_trade)

    assert realized_pnl == Decimal("60.00")


@pytest.mark.django_db
def test_calculate_unrealized_pnl_uses_market_api():
    Position.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        quantity=100,
        cost_price=Decimal("58.50"),
        weighted_avg_cost=Decimal("58.50"),
        total_invested=Decimal("5850"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )

    unrealized_pnl = CostCalculator(FakeMarketAPI()).calculate_unrealized_pnl("02610")

    assert unrealized_pnl == Decimal("150.00")


@pytest.mark.django_db
def test_get_hk_stock_stats_returns_expected_summary():
    Position.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        quantity=100,
        cost_price=Decimal("58.50"),
        weighted_avg_cost=Decimal("58.50"),
        total_invested=Decimal("5850"),
        realized_pnl=Decimal("25.00"),
        status=Position.Status.ACTIVE,
    )

    stats = CostCalculator(FakeMarketAPI()).get_hk_stock_stats("02610")

    assert stats["stock_code"] == "02610"
    assert stats["market_value"] == Decimal("6000.00")
    assert stats["unrealized_pnl"] == Decimal("150.00")
    assert stats["daily_pnl"] == Decimal("100.00")
    assert stats["realized_pnl"] == Decimal("25.00")


@pytest.mark.django_db
def test_get_hk_stock_stats_falls_back_when_market_api_raises():
    Position.objects.create(
        stock_code="02610",
        stock_name="鍗楀北閾濅笟鍥介檯",
        market=TradeRecord.Market.HK_STOCK,
        quantity=100,
        cost_price=Decimal("58.50"),
        weighted_avg_cost=Decimal("58.50"),
        total_invested=Decimal("5850"),
        realized_pnl=Decimal("25.00"),
        status=Position.Status.ACTIVE,
    )

    stats = CostCalculator(BrokenSnapshotMarketAPI()).get_hk_stock_stats("02610")

    assert stats["market_value"] == Decimal("5850.00")
    assert stats["unrealized_pnl"] == Decimal("0.00")
    assert stats["daily_pnl"] == Decimal("0.00")


@pytest.mark.django_db
def test_get_hk_stock_stats_accounts_for_same_day_buy_cash_flow():
    Position.objects.create(
        stock_code="01712",
        stock_name="龙资源",
        market=TradeRecord.Market.HK_STOCK,
        quantity=5000,
        cost_price=Decimal("8.6612"),
        weighted_avg_cost=Decimal("8.6612"),
        total_invested=Decimal("43306.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    TradeRecord.objects.create(
        stock_code="01712",
        stock_name="龙资源",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("8.2700"),
        quantity=1000,
        trade_time=timezone.make_aware(datetime.datetime(2026, 4, 24, 14, 23, 58), timezone.get_current_timezone()),
        source=TradeRecord.Source.HSBC_EMAIL,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
    )

    stats = CostCalculator(HKSnapshotMarketAPI()).get_hk_stock_stats("01712")

    assert stats["daily_pnl"] == Decimal("280.00")


@pytest.mark.django_db
def test_trade_recorder_updates_position_automatically():
    recorder = TradeRecorder()
    trade_time = timezone.now()

    trade, created = recorder.record_trade(
        {
            "stock_code": "603063",
            "stock_name": "禾望电气",
            "market": TradeRecord.Market.A_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": Decimal("41.43"),
            "quantity": 100,
            "trade_time": trade_time,
            "source": TradeRecord.Source.THS,
            "commission": Decimal("0"),
            "stamp_duty": Decimal("0"),
            "other_fees": Decimal("0"),
        }
    )

    assert created is True
    position = Position.objects.get(stock_code="603063")
    assert position.quantity == 100
    assert position.weighted_avg_cost == Decimal("41.43")
