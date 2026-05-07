from __future__ import annotations

from celery import shared_task

from config.trading_calendar import is_cn_equity_trading_day
from portfolio.services.market_snapshot_service import MarketSnapshotService
from portfolio.services.portfolio_analytics import PortfolioAnalyticsService
from django.utils import timezone


@shared_task
def refresh_market_price_snapshots():
    today = timezone.localdate()
    if not is_cn_equity_trading_day(today):
        return {"skipped": True, "reason": "non_trading_day", "trade_date": today.isoformat()}

    result = MarketSnapshotService().refresh_snapshots()
    PortfolioAnalyticsService().get_overview()
    return result
