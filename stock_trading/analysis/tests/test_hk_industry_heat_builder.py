from decimal import Decimal

import pandas as pd
from django.utils import timezone

from analysis.services.industry_heat_builder import IndustryHeatSnapshotBuilder
from trades.models import TradeRecord


class FakeTushareClient:
    is_available = True

    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def call(self, method, cache_key=None, **kwargs):
        self.calls.append((method, kwargs))
        key = (method, tuple(sorted(kwargs.items())))
        return self.frames.get(key, self.frames.get(method))


class FakeMarketAPI:
    def fetch_daily_bars(self, stock_code, start, end, market):
        assert market == TradeRecord.Market.HK_STOCK
        return [
            {"trade_date": "20260418", "close": 7.80},
            {"trade_date": "20260421", "close": 8.02},
            {"trade_date": "20260422", "close": 8.10},
            {"trade_date": "20260423", "close": 8.22},
            {"trade_date": "20260424", "close": 8.31},
        ]


def test_hk_industry_heat_builder_maps_hk_stock_to_hk_industry():
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
    frames = {
        "ths_index": pd.DataFrame(
            [
                {"ts_code": "871006.TI", "name": "金属与采矿", "type": "I"},
            ]
        ),
        "ths_member": pd.DataFrame(
            [
                {"ts_code": "871006.TI", "con_code": "1712.HK", "con_name": "龙资源"},
            ]
        ),
        "ths_daily": pd.DataFrame(
            [
                {"ts_code": "871006.TI", "trade_date": "20260424", "close": 1110.0, "pct_change": 1.25, "turnover_rate": 0.82},
                {"ts_code": "871006.TI", "trade_date": "20260423", "close": 1102.0, "pct_change": 0.35, "turnover_rate": 0.78},
                {"ts_code": "871006.TI", "trade_date": "20260422", "close": 1095.0, "pct_change": 0.12, "turnover_rate": 0.81},
                {"ts_code": "871006.TI", "trade_date": "20260421", "close": 1086.0, "pct_change": 0.56, "turnover_rate": 0.74},
                {"ts_code": "871006.TI", "trade_date": "20260418", "close": 1072.0, "pct_change": -0.20, "turnover_rate": 0.69},
            ]
        ),
    }

    builder = IndustryHeatSnapshotBuilder(
        tushare_client=FakeTushareClient(frames),
        market_api=FakeMarketAPI(),
    )

    result = builder.build(trade)

    assert result["industry_ts_code"] == "871006.TI"
    assert result["industry_name"] == "金属与采矿"
    assert result["heat_level"] == "hot"
    assert result["security_position"] in {"leading", "in_line", "lagging"}
    assert result["degraded"] is False
