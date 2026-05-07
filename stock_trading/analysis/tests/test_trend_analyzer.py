from decimal import Decimal
from types import SimpleNamespace

from analysis.services.trend_analyzer import TrendAnalyzer
from trades.models import TradeRecord


class FakeMarketAPI:
    provider_name = "tushare_daily"

    def __init__(self, bars):
        self.bars = bars

    def fetch_daily_bars(self, stock_code, start, end, market):
        assert stock_code == "603063"
        assert market == TradeRecord.Market.A_STOCK
        return list(self.bars)


class FakeHKMarketAPI:
    provider_name = "tushare_hk_daily"

    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def fetch_daily_bars(self, stock_code, start, end, market):
        self.calls.append((stock_code, market))
        assert market == TradeRecord.Market.HK_STOCK
        return list(self.bars)


def make_bar(day: int, close: float):
    return {
        "trade_date": f"202603{day:02d}",
        "open": close - 0.1,
        "high": close + 0.2,
        "low": close - 0.3,
        "close": close,
        "pre_close": close - 0.05,
        "volume": 1000 + day * 10,
        "amount": 10000 + day * 200,
    }


def test_trend_analyzer_uses_daily_bars_for_a_share():
    bars = [make_bar(day, 10 + day * 0.1) for day in range(1, 31)]
    bars += [
        {
            "trade_date": f"202604{day:02d}",
            "open": 13 + day * 0.2 - 0.1,
            "high": 13 + day * 0.2 + 0.2,
            "low": 13 + day * 0.2 - 0.4,
            "close": 13 + day * 0.2,
            "pre_close": 13 + (day - 1) * 0.2,
            "volume": 1600 + day * 20,
            "amount": 18000 + day * 400,
        }
        for day in range(1, 31)
    ]
    analyzer = TrendAnalyzer(market_api=FakeMarketAPI(bars))
    trade = SimpleNamespace(
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("41.4300"),
        quantity=100,
        trade_time="2026-04-22T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["data_source"] == "tushare_daily"
    assert result["degraded"] is False
    assert result["ma5"] >= result["ma10"]
    assert result["ma10"] >= result["ma20"]
    assert "macd" in result
    assert "rsi14" in result
    assert "k_value" in result
    assert result["trend_phase"] in {"uptrend", "breakout_attempt", "rebound"}
    assert len(result["price_chart"]) == len(bars)
    assert result["price_chart"][-1]["trade_date"] == bars[-1]["trade_date"]
    assert result["price_chart"][-1]["open"] == bars[-1]["open"]
    assert result["price_chart"][-1]["high"] == bars[-1]["high"]
    assert result["price_chart"][-1]["low"] == bars[-1]["low"]
    assert result["price_chart"][-1]["close"] == bars[-1]["close"]
    assert "ma20" in result["price_chart"][-1]


def test_trend_analyzer_marks_hk_as_degraded_without_real_source():
    analyzer = TrendAnalyzer()
    trade = SimpleNamespace(
        stock_code="00189",
        stock_name="Dongyue",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("11.5750"),
        quantity=2000,
        trade_time="2026-04-22T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["degraded"] is True
    assert "港股" in result["degraded_reason"]
    assert result["price_chart"] == []


def test_trend_analyzer_uses_tushare_daily_bars_for_normal_hk_stock():
    bars = [make_bar(day, 11 + day * 0.08) for day in range(1, 40)]
    analyzer = TrendAnalyzer(market_api=FakeHKMarketAPI(bars))
    trade = SimpleNamespace(
        stock_code="00189",
        stock_name="Dongyue",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("12.3000"),
        quantity=2000,
        trade_time="2026-04-24T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["data_source"] == "tushare_hk_daily"
    assert result["degraded"] is False
    assert len(result["price_chart"]) == len(bars)
    assert result["trend_phase"] in {"uptrend", "breakout_attempt", "rebound", "range_bound"}


def test_trend_analyzer_keeps_special_hk_etf_on_fallback():
    analyzer = TrendAnalyzer(market_api=FakeHKMarketAPI([]))
    trade = SimpleNamespace(
        stock_code="07226",
        stock_name="XL HSTECH",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("3.8440"),
        quantity=1700,
        trade_time="2026-04-24T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["data_source"] == "fallback_heuristic"
    assert result["degraded"] is True
    assert result["price_chart"] == []
