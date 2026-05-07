from decimal import Decimal
from types import SimpleNamespace

from analysis.services.volume_analyzer import VolumeAnalyzer
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


def make_bar(day: int, close: float, pre_close: float, volume: float, amount: float):
    return {
        "trade_date": f"202604{day:02d}",
        "open": close,
        "high": close + 0.3,
        "low": close - 0.2,
        "close": close,
        "pre_close": pre_close,
        "volume": volume,
        "amount": amount,
    }


def test_volume_analyzer_uses_market_daily_bars_for_a_share():
    bars = [make_bar(day, 10 + day * 0.1, 9.9 + day * 0.1, 1000 + day * 10, 10000 + day * 300) for day in range(1, 22)]
    bars[-1] = make_bar(22, 13.2, 12.6, 2200, 42000)
    analyzer = VolumeAnalyzer(market_api=FakeMarketAPI(bars))
    trade = SimpleNamespace(
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("41.4300"),
        quantity=100,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time="2026-04-22T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["data_source"] == "tushare_daily"
    assert result["degraded"] is False
    assert result["daily_volume"] == 2200.0
    assert result["volume_signal"] == "high"
    assert "volume_ratio_20" in result
    assert result["volume_pattern"] in {"放量上涨", "放量突破"}
    assert len(result["volume_chart"]) == len(bars)
    assert result["volume_chart"][-1]["trade_date"] == "20260422"
    assert "avg_volume_20" in result["volume_chart"][-1]


def test_volume_analyzer_marks_hk_as_degraded_without_real_source():
    analyzer = VolumeAnalyzer()
    trade = SimpleNamespace(
        stock_code="00189",
        stock_name="Dongyue",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("11.5750"),
        quantity=2000,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time="2026-04-22T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["degraded"] is True
    assert "港股" in result["degraded_reason"]
    assert result["volume_chart"] == []


def test_volume_analyzer_uses_tushare_daily_bars_for_normal_hk_stock():
    bars = [make_bar(day, 11 + day * 0.05, 10.9 + day * 0.05, 1000 + day * 20, 20000 + day * 400) for day in range(1, 22)]
    bars[-1] = make_bar(22, 12.3, 11.38, 9645821, 110282381.05)
    analyzer = VolumeAnalyzer(market_api=FakeHKMarketAPI(bars))
    trade = SimpleNamespace(
        stock_code="00189",
        stock_name="Dongyue",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("12.3000"),
        quantity=2000,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time="2026-04-24T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["data_source"] == "tushare_hk_daily"
    assert result["degraded"] is False
    assert result["daily_volume"] == 9645821.0
    assert len(result["volume_chart"]) == len(bars)


def test_volume_analyzer_keeps_special_hk_etf_on_fallback():
    analyzer = VolumeAnalyzer(market_api=FakeHKMarketAPI([]))
    trade = SimpleNamespace(
        stock_code="07709",
        stock_name="XL Hynix",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("42.6800"),
        quantity=300,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
        trade_time="2026-04-24T10:00:00+08:00",
    )

    result = analyzer.analyze(trade)

    assert result["data_source"] == "fallback_heuristic"
    assert result["degraded"] is True
    assert result["volume_chart"] == []
