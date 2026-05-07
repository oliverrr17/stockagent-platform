from datetime import date, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from portfolio.models import CashAccount, CashFlow, Position, SecurityPriceSnapshot
from portfolio.services.market_snapshot_service import MarketSnapshotService
from portfolio.services.portfolio_analytics import PortfolioAnalyticsService
from trades.models import TradeRecord


class FakeMarketDataProvider:
    provider_name = "fake_market_data"

    def __init__(self, bars=None, snapshots=None, fx_rates=None):
        self.bars = bars or {}
        self.snapshots = snapshots or {}
        self.fx_rates = fx_rates or {}

    def fetch_daily_bars(self, stock_code, start, end, market):
        return self.bars.get((stock_code, market), [])

    def get_snapshot(self, stock_code, market):
        return self.snapshots.get((stock_code, market), {})

    def get_fx_rate(self, base_currency, quote_currency, rate_date):
        return self.fx_rates[(base_currency, quote_currency, str(rate_date))]


@pytest.mark.django_db
def test_market_snapshot_service_persists_daily_bars_and_etf_snapshots():
    Position.objects.create(
        stock_code="603063",
        stock_name="禾望电气",
        market=TradeRecord.Market.A_STOCK,
        quantity=300,
        cost_price=Decimal("39.2010"),
        weighted_avg_cost=Decimal("39.2010"),
        total_invested=Decimal("11760.3000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    Position.objects.create(
        stock_code="07709",
        stock_name="ＸＬ二南方海力士",
        market=TradeRecord.Market.HK_STOCK,
        quantity=300,
        cost_price=Decimal("17.8940"),
        weighted_avg_cost=Decimal("17.8940"),
        total_invested=Decimal("5368.2000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )

    provider = FakeMarketDataProvider(
        bars={
            ("603063", TradeRecord.Market.A_STOCK): [
                {
                    "trade_date": "20260423",
                    "open": 41.78,
                    "high": 42.97,
                    "low": 41.50,
                    "close": 41.79,
                    "pre_close": 41.77,
                    "volume": 363085.45,
                    "amount": 1530901.016,
                },
                {
                    "trade_date": "20260424",
                    "open": 42.42,
                    "high": 42.55,
                    "low": 40.23,
                    "close": 40.70,
                    "pre_close": 41.79,
                    "volume": 388271.1,
                    "amount": 1589490.751,
                },
            ]
        },
        snapshots={
            ("07709", TradeRecord.Market.HK_STOCK): {
                "latest_price": 42.68,
                "previous_close": 42.50,
                "trade_date": "2026-04-24",
                "open": 42.46,
                "high": 43.12,
                "low": 40.90,
                "volume": 33261851.0,
                "amount": 1406079214.0,
                "data_source": "sina_hk_quote",
                "degraded": True,
                "degraded_reason": "web quote",
            }
        },
    )

    result = MarketSnapshotService(provider).refresh_snapshots(end_date=date(2026, 4, 24))

    assert result["securities"] == 2
    assert SecurityPriceSnapshot.objects.filter(stock_code="603063", trade_date=date(2026, 4, 23)).exists()
    etf_snapshot = SecurityPriceSnapshot.objects.get(stock_code="07709", trade_date=date(2026, 4, 24))
    assert etf_snapshot.close_price == Decimal("42.6800")
    assert etf_snapshot.previous_close == Decimal("42.5000")
    assert etf_snapshot.source == "sina_hk_quote"
    assert etf_snapshot.degraded is True


@pytest.mark.django_db
def test_market_snapshot_service_prefers_special_etf_snapshot_for_end_date_even_when_bars_exist():
    Position.objects.create(
        stock_code="07709",
        stock_name="ETF",
        market=TradeRecord.Market.HK_STOCK,
        quantity=300,
        cost_price=Decimal("17.8940"),
        weighted_avg_cost=Decimal("17.8940"),
        total_invested=Decimal("5368.2000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    provider = FakeMarketDataProvider(
        bars={
            ("07709", TradeRecord.Market.HK_STOCK): [
                {
                    "trade_date": "20260505",
                    "open": 58.54,
                    "high": 60.60,
                    "low": 58.40,
                    "close": 60.00,
                    "pre_close": 58.54,
                    "volume": 20834304.0,
                    "amount": 1241480144.0,
                },
                {
                    "trade_date": "20260506",
                    "open": 69.00,
                    "high": 72.84,
                    "low": 69.00,
                    "close": 71.90,
                    "pre_close": 60.00,
                    "volume": 70704920.0,
                    "amount": 5029347072.0,
                },
            ]
        },
        snapshots={
            ("07709", TradeRecord.Market.HK_STOCK): {
                "latest_price": 71.80,
                "previous_close": 60.00,
                "trade_date": "2026-05-06",
                "open": 69.00,
                "high": 72.84,
                "low": 69.00,
                "volume": 70587920.0,
                "amount": 5020934712.0,
                "data_source": "sina_hk_quote",
                "degraded": True,
                "degraded_reason": "web quote",
            }
        },
    )

    MarketSnapshotService(provider).refresh_snapshots(end_date=date(2026, 5, 6))

    snapshot = SecurityPriceSnapshot.objects.get(stock_code="07709", trade_date=date(2026, 5, 6))
    assert snapshot.close_price == Decimal("71.8000")
    assert snapshot.source == "sina_hk_quote"
    assert snapshot.degraded is True


@pytest.mark.django_db
def test_portfolio_analytics_cash_balances_include_trade_cash_flow():
    account = CashAccount.objects.create(currency=CashAccount.Currency.HKD)
    CashFlow.objects.create(
        cash_account=account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("50000"),
        occurred_at=timezone.make_aware(datetime(2026, 4, 23, 9, 0, 0), timezone.get_current_timezone()),
        note="initial capital",
    )
    TradeRecord.objects.create(
        stock_code="01712",
        stock_name="龍資源",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("8.2700"),
        quantity=1000,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time=timezone.make_aware(datetime(2026, 4, 24, 14, 23, 58), timezone.get_current_timezone()),
        source=TradeRecord.Source.HSBC_EMAIL,
    )
    provider = FakeMarketDataProvider(
        fx_rates={("HKD", "CNY", "2026-04-24"): Decimal("0.8765")},
    )

    balances = PortfolioAnalyticsService(provider).get_cash_balances(date(2026, 4, 24))

    assert balances["HKD"]["balance"] == Decimal("41730")
