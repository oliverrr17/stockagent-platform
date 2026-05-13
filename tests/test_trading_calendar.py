from datetime import date

from django.core.cache import cache

from config.trading_calendar import is_cn_equity_trading_day, is_hk_equity_trading_day


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return list(self.rows)


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def trade_cal(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFrame(self.rows)


def test_trading_calendar_marks_weekend_as_closed():
    cache.clear()
    assert is_cn_equity_trading_day(date(2026, 4, 25), token="", client=None) is False


def test_trading_calendar_uses_tushare_trade_cal_when_available():
    cache.clear()
    client = FakeClient([{"cal_date": "20260427", "is_open": 0}])

    assert is_cn_equity_trading_day(date(2026, 4, 27), token="demo", client=client) is False
    assert client.calls[0]["exchange"] == "SSE"
    assert client.calls[0]["start_date"] == "20260427"


def test_hk_trading_calendar_marks_weekend_as_closed():
    cache.clear()
    assert is_hk_equity_trading_day(date(2026, 4, 25), token="", client=None) is False


def test_hk_trading_calendar_uses_tushare_trade_cal_when_available():
    cache.clear()
    client = FakeClient([{"cal_date": "20260513", "is_open": 0}])

    assert is_hk_equity_trading_day(date(2026, 5, 13), token="demo", client=client) is False
    assert client.calls[0]["exchange"] == "XHKG"
    assert client.calls[0]["start_date"] == "20260513"
