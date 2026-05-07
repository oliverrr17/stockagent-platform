from decimal import Decimal

from django.utils import timezone

from analysis.services.chip_analyzer import ChipAnalyzer
from trades.models import TradeRecord


class FakeMarketAPI:
    def fetch_daily_bars(self, stock_code, start, end, market):
        assert market == TradeRecord.Market.A_STOCK
        return [
            {
                "trade_date": "20260423",
                "open": 9.50,
                "high": 9.90,
                "low": 9.40,
                "close": 9.77,
                "pre_close": 9.52,
                "volume": 1010898.34,
                "amount": 995691.631,
                "data_source": "tushare_daily",
            }
        ]


class FakeTushareClient:
    is_available = True

    def __init__(self):
        self.calls = []

    def call(self, method, cache_key=None, **kwargs):
        self.calls.append((method, kwargs))
        if method == "cyq_perf":
            return type(
                "FakeFrame",
                (),
                {
                    "iloc": [
                        {
                            "trade_date": "20260423",
                            "weight_avg": 11.11,
                            "winner_rate": 0.18,
                            "cost_5pct": 9.80,
                            "cost_15pct": 10.00,
                            "cost_50pct": 11.00,
                            "cost_85pct": 12.50,
                            "cost_95pct": 12.90,
                        }
                    ],
                    "__len__": lambda self: 1,
                },
            )()
        if method == "cyq_chips":
            return type(
                "FakeFrame",
                (),
                {
                    "to_dict": lambda self, orient: [
                        {"price": 9.5, "percent": 0.10},
                        {"price": 10.0, "percent": 0.25},
                        {"price": 11.0, "percent": 0.30},
                        {"price": 12.0, "percent": 0.20},
                        {"price": 12.5, "percent": 0.15},
                    ],
                    "__len__": lambda self: 5,
                },
            )()
        raise AssertionError(f"unexpected method: {method}")


def test_chip_analyzer_uses_real_a_share_cyq_data():
    analyzer = ChipAnalyzer(
        market_api=FakeMarketAPI(),
        tushare_client=FakeTushareClient(),
    )
    trade = TradeRecord(
        stock_code="600873",
        stock_name="梅花生物",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("9.7700"),
        quantity=800,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    result = analyzer.analyze(trade)

    assert result["data_source"] == "tushare_cyq"
    assert result["degraded"] is False
    assert result["reference_price"] == 9.77
    assert result["position_zone"] == "value_zone"
    assert result["winner_rate"] == 0.18
    assert result["weight_avg"] == 11.11
    assert result["chip_concentration"] > 0
