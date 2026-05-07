from decimal import Decimal

import pytest
from django.utils import timezone

from portfolio.models import Position, PositionEntry
from portfolio.services.portfolio_manager import PortfolioManager
from trades.models import TradeRecord


@pytest.mark.django_db
def test_add_position_creates_entry_and_position():
    manager = PortfolioManager()

    position = manager.add_position(
        {
            "stock_code": "02610",
            "stock_name": "南山铝业国际",
            "market": TradeRecord.Market.HK_STOCK,
            "quantity": 100,
            "cost_price": Decimal("58.50"),
            "entry_time": timezone.now(),
        }
    )

    assert PositionEntry.objects.count() == 1
    assert position.stock_code == "02610"
    assert position.quantity == 100
    assert position.weighted_avg_cost == Decimal("58.50")
    assert position.status == Position.Status.ACTIVE


@pytest.mark.django_db
def test_add_position_rejects_invalid_stock_code():
    manager = PortfolioManager()

    with pytest.raises(ValueError, match="Invalid A-stock code"):
        manager.add_position(
            {
                "stock_code": "ABC123",
                "stock_name": "Invalid",
                "market": TradeRecord.Market.A_STOCK,
                "quantity": 100,
                "cost_price": Decimal("10"),
                "entry_time": timezone.now(),
            }
        )


@pytest.mark.django_db
def test_apply_trade_buy_then_sell_updates_position_and_realized_pnl():
    manager = PortfolioManager()
    buy_trade = TradeRecord.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("58.50"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.HSBC_EMAIL,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
    )
    sell_trade = TradeRecord.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("60.00"),
        quantity=40,
        trade_time=timezone.now(),
        source=TradeRecord.Source.HSBC_EMAIL,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
    )

    manager.apply_trade(buy_trade)
    position = Position.objects.get(stock_code="02610")
    assert position.quantity == 100
    assert position.weighted_avg_cost == Decimal("58.50")

    manager.apply_trade(sell_trade)
    position.refresh_from_db()
    assert position.quantity == 60
    assert position.status == Position.Status.ACTIVE
    assert position.realized_pnl == Decimal("60.00")


@pytest.mark.django_db
def test_apply_trade_marks_position_cleared_when_quantity_reaches_zero():
    manager = PortfolioManager()
    buy_trade = TradeRecord.objects.create(
        stock_code="603063",
        stock_name="禾望电气",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("41.43"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )
    sell_trade = TradeRecord.objects.create(
        stock_code="603063",
        stock_name="禾望电气",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("42.00"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    manager.apply_trade(buy_trade)
    manager.apply_trade(sell_trade)

    position = Position.objects.get(stock_code="603063")
    assert position.quantity == 0
    assert position.status == Position.Status.CLEARED


@pytest.mark.django_db
def test_apply_trade_rejects_sell_without_enough_quantity():
    manager = PortfolioManager()
    buy_trade = TradeRecord.objects.create(
        stock_code="603063",
        stock_name="禾望电气",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("41.43"),
        quantity=50,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )
    sell_trade = TradeRecord.objects.create(
        stock_code="603063",
        stock_name="禾望电气",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("42.00"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    manager.apply_trade(buy_trade)

    with pytest.raises(ValueError, match="Insufficient position quantity"):
        manager.apply_trade(sell_trade)
