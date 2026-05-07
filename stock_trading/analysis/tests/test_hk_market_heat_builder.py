from decimal import Decimal

import pandas as pd
from django.utils import timezone

from analysis.services.market_heat_builder import MarketHeatSnapshotBuilder
from trades.models import TradeRecord


class FakeTushareClient:
    is_available = True

    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def call(self, method, cache_key=None, **kwargs):
        self.calls.append((method, kwargs))
        return self.frames.get(method)


def test_hk_market_heat_builder_uses_ggt_and_hk_hold():
    trade = TradeRecord(
        stock_code="01712",
        stock_name="龙资源",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("8.2700"),
        quantity=1000,
        trade_time=timezone.now(),
        source=TradeRecord.Source.HSBC_EMAIL,
    )
    builder = MarketHeatSnapshotBuilder(
        tushare_client=FakeTushareClient(
            {
                "ggt_daily": pd.DataFrame(
                    [
                        {
                            "trade_date": "20260424",
                            "buy_amount": 350.09,
                            "buy_volume": 62.47,
                            "sell_amount": 301.26,
                            "sell_volume": 53.55,
                        }
                    ]
                ),
                "hk_hold": pd.DataFrame(
                    [
                        {"code": "1", "trade_date": "20260424", "ts_code": "00001.HK", "name": "长和", "vol": 90773590, "ratio": 2.36, "exchange": "HK"},
                        {"code": "5", "trade_date": "20260424", "ts_code": "00005.HK", "name": "汇丰控股", "vol": 120000000, "ratio": 3.12, "exchange": "HK"},
                    ]
                ),
            }
        )
    )

    result = builder.build(trade)

    assert result["market"] == TradeRecord.Market.HK_STOCK
    assert result["benchmark_ts_code"] == "southbound_connect"
    assert result["risk_preference"] == "risk_on"
    assert result["activity_level"] == "active"
    assert result["net_flow"] == 48.83
    assert result["holdings_count"] == 2
    assert result["degraded"] is False
