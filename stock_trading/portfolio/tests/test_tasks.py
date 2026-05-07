from unittest.mock import patch

import pytest

from portfolio.tasks import refresh_market_price_snapshots


@pytest.mark.django_db
def test_refresh_market_price_snapshots_skips_on_non_trading_day():
    with (
        patch("portfolio.tasks.is_cn_equity_trading_day", return_value=False),
        patch("portfolio.tasks.MarketSnapshotService") as market_snapshot_service,
        patch("portfolio.tasks.PortfolioAnalyticsService") as analytics_service,
    ):
        result = refresh_market_price_snapshots()

    assert result["skipped"] is True
    market_snapshot_service.assert_not_called()
    analytics_service.assert_not_called()
