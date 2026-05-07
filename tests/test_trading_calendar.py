from datetime import date

from config.trading_calendar import is_cn_equity_trading_day


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
    assert is_cn_equity_trading_day(date(2026, 4, 25), token="", client=None) is False


def test_trading_calendar_uses_tushare_trade_cal_when_available():
    client = FakeClient([{"cal_date": "20260427", "is_open": 0}])

    assert is_cn_equity_trading_day(date(2026, 4, 27), token="demo", client=client) is False
    assert client.calls[0]["exchange"] == "SSE"
    assert client.calls[0]["start_date"] == "20260427"

