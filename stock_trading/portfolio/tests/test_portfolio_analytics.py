from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from portfolio.models import (
    CashAccount,
    CashFlow,
    FXRate,
    PortfolioPerformanceSnapshot,
    Position,
    PositionDailyContributionSnapshot,
    SecurityPriceSnapshot,
)
from portfolio.services.portfolio_analytics import PortfolioAnalyticsService
from trades.models import TradeRecord


@dataclass
class FakeMarketDataProvider:
    snapshots: dict
    fx_rates: dict
    daily_bars: dict | None = None

    def get_snapshot(self, stock_code: str, market: str):
        return self.snapshots[(stock_code, market)]

    def get_fx_rate(self, base_currency: str, quote_currency: str, rate_date):
        return self.fx_rates[(base_currency, quote_currency, str(rate_date))]

    def fetch_daily_bars(self, stock_code: str, start, end, market: str):
        return (self.daily_bars or {}).get((stock_code, market, str(end)), [])


@pytest.mark.django_db
def test_portfolio_analytics_builds_overview_with_fx_and_cash_flows():
    cny_account = CashAccount.objects.create(currency=CashAccount.Currency.CNY)
    hkd_account = CashAccount.objects.create(currency=CashAccount.Currency.HKD)
    today = timezone.localdate()
    occurred_at = timezone.make_aware(datetime.combine(today, datetime.min.time()))

    CashFlow.objects.create(
        cash_account=cny_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("100000"),
        occurred_at=occurred_at,
        note="期初人民币",
    )
    CashFlow.objects.create(
        cash_account=hkd_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("10000"),
        occurred_at=occurred_at,
        note="期初港币",
    )
    FXRate.objects.create(
        base_currency="HKD",
        quote_currency="CNY",
        rate_date=today,
        rate=Decimal("0.9100"),
        source="AKSHARE_BOC",
    )
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
        stock_code="00189",
        stock_name="东岳集团",
        market=TradeRecord.Market.HK_STOCK,
        quantity=2000,
        cost_price=Decimal("11.5750"),
        weighted_avg_cost=Decimal("11.5750"),
        total_invested=Decimal("23150.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )

    provider = FakeMarketDataProvider(
        snapshots={
            ("603063", TradeRecord.Market.A_STOCK): {"latest_price": 42.50, "previous_close": 41.00},
            ("00189", TradeRecord.Market.HK_STOCK): {"latest_price": 12.50, "previous_close": 12.10},
        },
        fx_rates={("HKD", "CNY", str(today)): Decimal("0.9100")},
    )

    overview = PortfolioAnalyticsService(provider).get_overview(start_date=today)

    assert overview["base_currency"] == "CNY"
    assert Decimal(str(overview["cash_balances"]["CNY"]["balance"])) == Decimal("100000")
    assert Decimal(str(overview["cash_balances"]["HKD"]["balance"])) == Decimal("10000")
    assert Decimal(str(overview["positions_market_value_cny"])) > Decimal("0")
    assert Decimal(str(overview["total_assets_cny"])) > Decimal("100000")
    assert len(overview["curves"]["daily"]) == 1
    assert "daily" in overview["returns"]
    assert Decimal(str(overview["realized_pnl_cny"])) == Decimal("0")
    assert Decimal(str(overview["unrealized_pnl_cny"])) > Decimal("0")
    assert Decimal(str(overview["realized_pnl_cny"])) == Decimal("0")
    assert Decimal(str(overview["total_return_cny"])) == Decimal(str(overview["unrealized_pnl_cny"]))
    assert overview["returns"]["daily"] > 0
    assert overview["returns"]["monthly"] == overview["returns"]["daily"]
    assert overview["returns"]["yearly"] == overview["returns"]["daily"]


@pytest.mark.django_db
def test_portfolio_analytics_counts_realized_pnl_for_sell_after_start_date():
    today = timezone.localdate()
    occurred_at = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    cny_account = CashAccount.objects.create(currency=CashAccount.Currency.CNY)
    CashFlow.objects.create(
        cash_account=cny_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("5000"),
        occurred_at=occurred_at,
        note="期初现金",
    )
    Position.objects.create(
        stock_code="600873",
        stock_name="梅花生物",
        market=TradeRecord.Market.A_STOCK,
        quantity=0,
        cost_price=Decimal("11.7700"),
        weighted_avg_cost=Decimal("11.7700"),
        total_invested=Decimal("0"),
        realized_pnl=Decimal("0"),
        status=Position.Status.CLEARED,
    )
    TradeRecord.objects.create(
        stock_code="600873",
        stock_name="梅花生物",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("9.7700"),
        quantity=800,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    service = PortfolioAnalyticsService(FakeMarketDataProvider(snapshots={}, fx_rates={}))
    overview = service.get_overview(start_date=today)

    assert Decimal(str(overview["realized_pnl_cny"])) == Decimal("-1600")


@pytest.mark.django_db
def test_portfolio_analytics_uses_first_trading_day_pnl_at_system_start():
    today = timezone.localdate()
    occurred_at = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    cny_account = CashAccount.objects.create(currency=CashAccount.Currency.CNY)
    CashFlow.objects.create(
        cash_account=cny_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("10000"),
        occurred_at=occurred_at,
        note="bootstrap cash",
    )
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
    provider = FakeMarketDataProvider(
        snapshots={
            ("603063", TradeRecord.Market.A_STOCK): {"latest_price": 42.50, "previous_close": 41.00},
        },
        fx_rates={},
    )

    overview = PortfolioAnalyticsService(provider).get_overview(start_date=today)

    assert overview["returns"]["daily"] > 0
    assert overview["returns"]["monthly"] == overview["returns"]["daily"]
    assert overview["returns"]["yearly"] == overview["returns"]["daily"]


@pytest.mark.django_db
def test_portfolio_analytics_month_and_year_returns_start_from_zero_baseline_date():
    today = timezone.localdate()
    start_date = today - timedelta(days=1)
    occurred_at = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    cny_account = CashAccount.objects.create(currency=CashAccount.Currency.CNY)
    CashFlow.objects.create(
        cash_account=cny_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("10000"),
        occurred_at=occurred_at,
        note="bootstrap cash",
    )
    Position.objects.create(
        stock_code="600873",
        stock_name="梅花生物",
        market=TradeRecord.Market.A_STOCK,
        quantity=0,
        cost_price=Decimal("11.7700"),
        weighted_avg_cost=Decimal("11.7700"),
        total_invested=Decimal("0"),
        realized_pnl=Decimal("0"),
        status=Position.Status.CLEARED,
    )
    TradeRecord.objects.create(
        stock_code="600873",
        stock_name="梅花生物",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("9.7700"),
        quantity=800,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    provider = FakeMarketDataProvider(
        snapshots={
            ("600873", TradeRecord.Market.A_STOCK): {
                "latest_price": 9.77,
                "previous_close": 9.97,
                "trade_date": today.isoformat(),
            },
        },
        fx_rates={},
    )

    overview = PortfolioAnalyticsService(provider).get_overview(start_date=start_date)

    first_day_assets = Decimal(str(overview["curves"]["daily"][0]["total_assets_cny"]))
    second_day_assets = Decimal(str(overview["curves"]["daily"][1]["total_assets_cny"]))
    first_day_return = Decimal(str(overview["curves"]["daily"][0]["daily_return_pct"]))
    second_day_return = Decimal(str(overview["returns"]["daily"]))
    expected_cumulative = (
        (((Decimal("1") + first_day_return / Decimal("100")) * (Decimal("1") + second_day_return / Decimal("100"))) - Decimal("1"))
        * Decimal("100")
    ).quantize(Decimal("0.0001"))

    assert Decimal(str(overview["returns"]["daily"])) == second_day_return
    assert abs(Decimal(str(overview["returns"]["monthly"])) - expected_cumulative) <= Decimal("0.0001")
    assert abs(Decimal(str(overview["returns"]["yearly"])) - expected_cumulative) <= Decimal("0.0001")
    assert abs(Decimal(str(overview["curves"]["daily"][1]["cumulative_return_pct"])) - expected_cumulative) <= Decimal("0.0001")


@pytest.mark.django_db
def test_portfolio_analytics_returns_active_and_cleared_positions():
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
        stock_code="600873",
        stock_name="梅花生物",
        market=TradeRecord.Market.A_STOCK,
        quantity=0,
        cost_price=Decimal("11.7700"),
        weighted_avg_cost=Decimal("11.7700"),
        total_invested=Decimal("0"),
        realized_pnl=Decimal("1600.0000"),
        status=Position.Status.CLEARED,
    )

    provider = FakeMarketDataProvider(
        snapshots={
            ("603063", TradeRecord.Market.A_STOCK): {"latest_price": 42.50, "previous_close": 41.00},
        },
        fx_rates={},
    )
    service = PortfolioAnalyticsService(provider)

    active_rows = service.get_position_analytics()
    cleared_rows = service.get_cleared_positions()

    assert len(active_rows) == 1
    assert active_rows[0]["stock_code"] == "603063"
    assert active_rows[0]["data_source"] == "fallback_cost"
    assert active_rows[0]["degraded"] is False
    assert len(cleared_rows) == 1
    assert cleared_rows[0]["stock_code"] == "600873"


@pytest.mark.django_db
def test_portfolio_analytics_uses_hk_previous_close_for_curve_when_hist_bars_unavailable():
    today = date(2026, 4, 24)
    yesterday = date(2026, 4, 23)
    Position.objects.create(
        stock_code="00189",
        stock_name="涓滃渤闆嗗洟",
        market=TradeRecord.Market.HK_STOCK,
        quantity=2000,
        cost_price=Decimal("11.5750"),
        weighted_avg_cost=Decimal("11.5750"),
        total_invested=Decimal("23150.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )

    provider = FakeMarketDataProvider(
        snapshots={
            (
                "00189",
                TradeRecord.Market.HK_STOCK,
            ): {
                "latest_price": 12.50,
                "previous_close": 12.10,
                "trade_date": today.isoformat(),
                "data_source": "akshare_hk_spot",
                "degraded": False,
                "degraded_reason": "",
            }
        },
        fx_rates={
            ("HKD", "CNY", str(yesterday)): Decimal("0.9100"),
            ("HKD", "CNY", str(today)): Decimal("0.9100"),
        },
        daily_bars={
            ("00189", TradeRecord.Market.HK_STOCK, str(yesterday)): [],
        },
    )

    overview = PortfolioAnalyticsService(provider).get_overview(start_date=yesterday)

    expected_previous_assets = (Decimal("12.10") * Decimal("2000") * Decimal("0.9100")).quantize(Decimal("0.0001"))
    expected_current_assets = (Decimal("12.50") * Decimal("2000") * Decimal("0.9100")).quantize(Decimal("0.0001"))
    expected_daily_return = (
        ((expected_current_assets - expected_previous_assets) / expected_previous_assets) * Decimal("100")
    ).quantize(Decimal("0.0001"))

    assert Decimal(str(overview["curves"]["daily"][0]["total_assets_cny"])) == expected_previous_assets
    assert Decimal(str(overview["returns"]["daily"])) == expected_daily_return


@pytest.mark.django_db
def test_position_analytics_zeroes_a_share_daily_pnl_when_snapshot_trade_date_is_stale():
    today = timezone.localdate()
    Position.objects.create(
        stock_code="603063",
        stock_name="绂炬湜鐢垫皵",
        market=TradeRecord.Market.A_STOCK,
        quantity=100,
        cost_price=Decimal("41.4300"),
        weighted_avg_cost=Decimal("41.4300"),
        total_invested=Decimal("4143.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )

    provider = FakeMarketDataProvider(
        snapshots={
            (
                "603063",
                TradeRecord.Market.A_STOCK,
            ): {
                "latest_price": 42.50,
                "previous_close": 41.00,
                "trade_date": (today - timedelta(days=1)).isoformat(),
                "data_source": "tushare_daily",
                "degraded": False,
                "degraded_reason": "",
            }
        },
        fx_rates={},
    )

    rows = PortfolioAnalyticsService(provider).get_position_analytics(as_of_date=today)

    assert rows[0]["daily_pnl_native"] == 0.0
    assert rows[0]["daily_pnl_cny"] == 0.0


@pytest.mark.django_db
def test_daily_pnl_for_date_excludes_future_day_buys_from_prior_day_end_quantity():
    target_date = timezone.localdate() - timedelta(days=1)
    next_day = target_date + timedelta(days=1)
    Position.objects.create(
        stock_code="01712",
        stock_name="龍資源",
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
        stock_name="龍資源",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("8.2700"),
        quantity=1000,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time=timezone.make_aware(datetime.combine(next_day, datetime.min.time()), timezone.get_current_timezone()),
        source=TradeRecord.Source.HSBC_EMAIL,
    )
    FXRate.objects.create(
        base_currency="HKD",
        quote_currency="CNY",
        rate_date=target_date,
        rate=Decimal("0.8765"),
        source="test",
    )
    provider = FakeMarketDataProvider(
        snapshots={
            ("01712", TradeRecord.Market.HK_STOCK): {
                "latest_price": 8.25,
                "previous_close": 8.58,
                "trade_date": target_date.isoformat(),
                "data_source": "tushare_hk_daily",
                "degraded": False,
                "degraded_reason": "",
            },
        },
        fx_rates={("HKD", "CNY", str(target_date)): Decimal("0.8765")},
    )

    daily_pnl = PortfolioAnalyticsService(provider)._daily_pnl_for_date(target_date)

    expected = ((Decimal("8.25") - Decimal("8.58")) * Decimal("4000") * Decimal("0.8765")).quantize(Decimal("0.0001"))
    assert daily_pnl.quantize(Decimal("0.0001")) == expected


@pytest.mark.django_db
def test_position_analytics_daily_pnl_accounts_for_same_day_buy_cash_flow():
    target_date = timezone.localdate() - timedelta(days=1)
    Position.objects.create(
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        quantity=500,
        cost_price=Decimal("39.6326"),
        weighted_avg_cost=Decimal("39.6326"),
        total_invested=Decimal("19816.3000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    TradeRecord.objects.create(
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("40.2800"),
        quantity=200,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time=timezone.make_aware(datetime.combine(target_date, datetime.min.time()), timezone.get_current_timezone()) + timedelta(hours=13, minutes=21, seconds=17),
        source=TradeRecord.Source.MANUAL,
    )
    provider = FakeMarketDataProvider(
        snapshots={
            ("603063", TradeRecord.Market.A_STOCK): {
                "latest_price": 40.70,
                "previous_close": 41.79,
                "trade_date": target_date.isoformat(),
                "data_source": "tushare_daily",
                "degraded": False,
                "degraded_reason": "",
            },
        },
        fx_rates={},
    )

    rows = PortfolioAnalyticsService(provider).get_position_analytics(as_of_date=target_date)

    assert rows[0]["daily_pnl_native"] == -243.0
    assert rows[0]["daily_pnl_cny"] == -243.0


@pytest.mark.django_db
def test_portfolio_analytics_persists_performance_snapshot():
    today = timezone.localdate()
    occurred_at = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    cny_account = CashAccount.objects.create(currency=CashAccount.Currency.CNY)
    CashFlow.objects.create(
        cash_account=cny_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("10000"),
        occurred_at=occurred_at,
        note="snapshot test",
    )
    Position.objects.create(
        stock_code="603063",
        stock_name="绂炬湜鐢垫皵",
        market=TradeRecord.Market.A_STOCK,
        quantity=100,
        cost_price=Decimal("41.4300"),
        weighted_avg_cost=Decimal("41.4300"),
        total_invested=Decimal("4143.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    provider = FakeMarketDataProvider(
        snapshots={
            ("603063", TradeRecord.Market.A_STOCK): {
                "latest_price": 42.50,
                "previous_close": 41.00,
                "trade_date": today.isoformat(),
                "data_source": "tushare_daily",
                "degraded": False,
                "degraded_reason": "",
            }
        },
        fx_rates={},
        daily_bars={},
    )

    overview = PortfolioAnalyticsService(provider).get_overview(start_date=today)
    snapshot = PortfolioPerformanceSnapshot.objects.get(snapshot_date=today)

    assert Decimal(str(snapshot.total_assets_cny)) == Decimal(str(overview["curves"]["daily"][-1]["total_assets_cny"]))
    assert Decimal(str(snapshot.daily_return_pct)) == Decimal(str(overview["returns"]["daily"]))
    assert Decimal(str(snapshot.monthly_return_pct)) == Decimal(str(overview["returns"]["monthly"]))
    assert Decimal(str(snapshot.yearly_return_pct)) == Decimal(str(overview["returns"]["yearly"]))


@pytest.mark.django_db
def test_portfolio_analytics_persists_audit_metadata_and_position_contributions():
    today = timezone.localdate()
    occurred_at = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    cny_account = CashAccount.objects.create(currency=CashAccount.Currency.CNY)
    CashFlow.objects.create(
        cash_account=cny_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("10000"),
        occurred_at=occurred_at,
        note="audit test",
    )
    Position.objects.create(
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        quantity=100,
        cost_price=Decimal("41.4300"),
        weighted_avg_cost=Decimal("41.4300"),
        total_invested=Decimal("4143.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    provider = FakeMarketDataProvider(
        snapshots={
            ("603063", TradeRecord.Market.A_STOCK): {
                "latest_price": 42.50,
                "previous_close": 41.00,
                "trade_date": today.isoformat(),
                "data_source": "tushare_daily",
                "degraded": False,
                "degraded_reason": "",
            }
        },
        fx_rates={},
        daily_bars={},
    )

    PortfolioAnalyticsService(provider).get_overview(start_date=today)
    snapshot = PortfolioPerformanceSnapshot.objects.get(snapshot_date=today)
    contribution = PositionDailyContributionSnapshot.objects.get(
        snapshot_date=today,
        stock_code="603063",
        market=TradeRecord.Market.A_STOCK,
    )

    assert snapshot.audit_status == "FINAL"
    assert Decimal(str(snapshot.external_flow_cny)) == Decimal("10000")
    assert Decimal(str(snapshot.computed_daily_pnl_cny)) == Decimal("150")
    assert contribution.audit_status == "FINAL"
    assert contribution.source_trade_date == today
    assert contribution.price_source == "tushare_daily"
    assert contribution.degraded is False
    assert Decimal(str(contribution.daily_pnl_cny)) == Decimal("150")


@pytest.mark.django_db
def test_portfolio_analytics_marks_snapshot_provisional_when_degraded_price_used():
    today = timezone.localdate()
    occurred_at = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    hkd_account = CashAccount.objects.create(currency=CashAccount.Currency.HKD)
    CashFlow.objects.create(
        cash_account=hkd_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("5000"),
        occurred_at=occurred_at,
        note="provisional test",
    )
    Position.objects.create(
        stock_code="07709",
        stock_name="ETF",
        market=TradeRecord.Market.HK_STOCK,
        quantity=100,
        cost_price=Decimal("17.8940"),
        weighted_avg_cost=Decimal("17.8940"),
        total_invested=Decimal("1789.4000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    FXRate.objects.create(
        base_currency="HKD",
        quote_currency="CNY",
        rate_date=today,
        rate=Decimal("0.8765"),
        source="test",
    )
    provider = FakeMarketDataProvider(
        snapshots={
            ("07709", TradeRecord.Market.HK_STOCK): {
                "latest_price": 42.68,
                "previous_close": 42.50,
                "trade_date": today.isoformat(),
                "data_source": "sina_hk_quote",
                "degraded": True,
                "degraded_reason": "web quote",
            }
        },
        fx_rates={("HKD", "CNY", str(today)): Decimal("0.8765")},
        daily_bars={},
    )

    PortfolioAnalyticsService(provider).get_overview(start_date=today)
    snapshot = PortfolioPerformanceSnapshot.objects.get(snapshot_date=today)
    contribution = PositionDailyContributionSnapshot.objects.get(
        snapshot_date=today,
        stock_code="07709",
        market=TradeRecord.Market.HK_STOCK,
    )

    assert snapshot.audit_status == "PROVISIONAL"
    assert contribution.audit_status == "PROVISIONAL"
    assert contribution.degraded is True
    assert contribution.degraded_reason == "web quote"


def test_period_return_pct_uses_period_baseline_for_month_and_year():
    service = PortfolioAnalyticsService(market_data_provider=None)
    daily_points = [
        {
            "date": "2025-12-31",
            "total_assets_cny": 0.0,
            "total_return_cny": 0.0,
            "daily_return_pct": 0.0,
            "monthly_return_pct": 0.0,
            "yearly_return_pct": 0.0,
            "cumulative_return_pct": 10.0,
        },
        {
            "date": "2026-04-30",
            "total_assets_cny": 0.0,
            "total_return_cny": 0.0,
            "daily_return_pct": 0.0,
            "monthly_return_pct": 0.0,
            "yearly_return_pct": 0.0,
            "cumulative_return_pct": 20.0,
        },
        {
            "date": "2026-05-10",
            "total_assets_cny": 0.0,
            "total_return_cny": 0.0,
            "daily_return_pct": 2.0,
            "monthly_return_pct": 0.0,
            "yearly_return_pct": 0.0,
            "cumulative_return_pct": 26.0,
        },
    ]

    monthly_return = service._period_return_pct(
        daily_points,
        period_start=datetime(2026, 5, 1).date(),
        current_date=datetime(2026, 5, 10).date(),
    )
    yearly_return = service._period_return_pct(
        daily_points,
        period_start=datetime(2026, 1, 1).date(),
        current_date=datetime(2026, 5, 10).date(),
    )

    assert monthly_return == 5.0
    assert yearly_return == 14.5455


@pytest.mark.django_db
def test_portfolio_analytics_skips_non_trading_days_without_real_market_snapshot():
    start_date = date(2026, 4, 23)
    end_date = date(2026, 4, 27)
    occurred_at = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    cny_account = CashAccount.objects.create(currency=CashAccount.Currency.CNY)
    CashFlow.objects.create(
        cash_account=cny_account,
        direction=CashFlow.Direction.DEPOSIT,
        amount=Decimal("10000"),
        occurred_at=occurred_at,
        note="curve baseline",
    )
    Position.objects.create(
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        quantity=100,
        cost_price=Decimal("41.4300"),
        weighted_avg_cost=Decimal("41.4300"),
        total_invested=Decimal("4143.0000"),
        realized_pnl=Decimal("0"),
        status=Position.Status.ACTIVE,
    )
    provider = FakeMarketDataProvider(
        snapshots={
            ("603063", TradeRecord.Market.A_STOCK): {
                "latest_price": 42.99,
                "previous_close": 40.70,
                "trade_date": end_date.isoformat(),
                "data_source": "tushare_realtime_quote_sina",
                "degraded": False,
                "degraded_reason": "",
            }
        },
        fx_rates={},
        daily_bars={
            ("603063", TradeRecord.Market.A_STOCK, "2026-04-23"): [
                {
                    "trade_date": "20260423",
                    "open": 41.78,
                    "high": 42.97,
                    "low": 41.50,
                    "close": 41.79,
                    "pre_close": 41.77,
                    "volume": 363085.45,
                    "amount": 1530901.016,
                }
            ],
            ("603063", TradeRecord.Market.A_STOCK, "2026-04-24"): [
                {
                    "trade_date": "20260424",
                    "open": 42.42,
                    "high": 42.55,
                    "low": 40.23,
                    "close": 40.70,
                    "pre_close": 41.79,
                    "volume": 388271.1,
                    "amount": 1589490.751,
                }
            ],
        },
    )

    overview = PortfolioAnalyticsService(provider).get_overview(start_date=start_date)

    assert [point["date"] for point in overview["curves"]["daily"]] == [
        "2026-04-23",
        "2026-04-24",
        "2026-04-27",
    ]


@pytest.mark.django_db
def test_snapshot_on_date_derives_missing_history_from_next_day_previous_close():
    SecurityPriceSnapshot.objects.create(
        stock_code="07709",
        stock_name="ETF",
        market=TradeRecord.Market.HK_STOCK,
        trade_date=date(2026, 4, 22),
        close_price=Decimal("43.2200"),
        previous_close=Decimal("43.2200"),
        source="manual_input",
        degraded=False,
        degraded_reason="",
    )
    SecurityPriceSnapshot.objects.create(
        stock_code="07709",
        stock_name="ETF",
        market=TradeRecord.Market.HK_STOCK,
        trade_date=date(2026, 4, 24),
        close_price=Decimal("42.6800"),
        previous_close=Decimal("42.5000"),
        source="sina_hk_quote",
        degraded=True,
        degraded_reason="web quote",
    )

    snapshot = PortfolioAnalyticsService(market_data_provider=None)._snapshot_on_date(
        "07709",
        TradeRecord.Market.HK_STOCK,
        date(2026, 4, 23),
    )

    assert snapshot["latest_price"] == Decimal("42.5000")
    assert snapshot["previous_close"] == Decimal("43.2200")
    assert snapshot["degraded_reason"] == "historical_snapshot_derived_from_next_day_previous_close"


@pytest.mark.django_db
def test_portfolio_analytics_skips_weekend_points_derived_from_next_day_snapshot():
    service = PortfolioAnalyticsService(market_data_provider=None)

    assert service._is_real_snapshot_for_target_date(
        {
            "latest_price": Decimal("40.7000"),
            "previous_close": Decimal("40.7000"),
            "trade_date": "2026-04-26",
            "data_source": "sina_hk_quote",
            "degraded": True,
            "degraded_reason": "historical_snapshot_derived_from_next_day_previous_close",
        },
        date(2026, 4, 26),
    ) is False


@pytest.mark.django_db
def test_snapshot_on_date_prefers_prior_stored_close_over_live_snapshot_for_historical_gap():
    SecurityPriceSnapshot.objects.create(
        stock_code="07709",
        stock_name="ETF",
        market=TradeRecord.Market.HK_STOCK,
        trade_date=date(2026, 4, 24),
        close_price=Decimal("42.6800"),
        previous_close=Decimal("42.5000"),
        source="sina_hk_quote",
        degraded=True,
        degraded_reason="web quote",
    )

    class LiveOnlyProvider:
        def get_snapshot(self, stock_code: str, market: str):
            return {
                "latest_price": 71.8,
                "previous_close": 60.0,
                "trade_date": "2026-05-06",
                "data_source": "sina_hk_quote",
                "degraded": True,
                "degraded_reason": "web quote",
            }

        def fetch_daily_bars(self, stock_code: str, start, end, market: str):
            return []

        def get_fx_rate(self, base_currency: str, quote_currency: str, rate_date):
            return Decimal("0.8765")

    snapshot = PortfolioAnalyticsService(LiveOnlyProvider())._snapshot_on_date(
        "07709",
        TradeRecord.Market.HK_STOCK,
        date(2026, 4, 27),
    )

    assert snapshot["latest_price"] == Decimal("42.6800")
    assert snapshot["previous_close"] == Decimal("42.6800")
    assert snapshot["degraded_reason"] == "historical_snapshot_missing_used_prior_stored_close"
