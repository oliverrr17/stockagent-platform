from datetime import date

from django.core.cache import cache

from analysis.services.market_data import (
    AShareTushareProvider,
    FXAkshareProvider,
    FallbackHKProvider,
    HKTushareProvider,
    HKAkshareProvider,
    HKWebScraperProvider,
)
from trades.models import TradeRecord


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return list(self._rows)

    @property
    def empty(self):
        return len(self._rows) == 0


class FakePro:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def daily(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFrame(self.rows)

    def hk_daily(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFrame(self.rows)


class FakeAkshare:
    def __init__(self, hk_hist_rows=None, hk_spot_rows=None, fx_rows=None, spot_error=None):
        self.hk_hist_rows = hk_hist_rows or []
        self.hk_spot_rows = hk_spot_rows or []
        self.fx_rows = fx_rows or []
        self.spot_error = spot_error
        self.hist_calls = 0
        self.spot_calls = 0
        self.fx_calls = 0

    def stock_hk_hist(self, **kwargs):
        self.hist_calls += 1
        return FakeFrame(self.hk_hist_rows)

    def stock_hk_spot(self):
        self.spot_calls += 1
        if self.spot_error is not None:
            raise self.spot_error
        return FakeFrame(self.hk_spot_rows)

    def currency_boc_sina(self, **kwargs):
        self.fx_calls += 1
        return FakeFrame(self.fx_rows)


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class FakeRealtimeQuoteFrame(FakeFrame):
    pass


def test_tushare_provider_maps_daily_rows_to_bars():
    fake_pro = FakePro(
        [
            {
                "trade_date": "20260422",
                "open": 10.0,
                "high": 10.8,
                "low": 9.9,
                "close": 10.5,
                "pre_close": 10.0,
                "vol": 120000,
                "amount": 950000,
            }
        ]
    )
    provider = AShareTushareProvider(token="demo-token", client=fake_pro)

    bars = provider.fetch_daily_bars(
        "603063",
        start=date(2026, 4, 1),
        end=date(2026, 4, 22),
        market=TradeRecord.Market.A_STOCK,
    )

    assert fake_pro.calls[0]["ts_code"] == "603063.SH"
    assert bars[0]["trade_date"] == "20260422"
    assert bars[0]["close"] == 10.5
    assert bars[0]["volume"] == 120000
    assert bars[0]["amount"] == 950000


def test_tushare_provider_prefers_realtime_quote_for_a_share_snapshot(monkeypatch):
    monkeypatch.setattr("analysis.services.market_data.is_cn_equity_trading_day", lambda value: True)
    provider = AShareTushareProvider(
        token="demo-token",
        client=FakePro([]),
        realtime_quote_fetcher=lambda **kwargs: FakeRealtimeQuoteFrame(
            [
                {
                    "TS_CODE": "603063.SH",
                    "DATE": "20260427",
                    "TIME": "12:21:51",
                    "OPEN": 40.35,
                    "PRE_CLOSE": 40.70,
                    "PRICE": 42.99,
                    "HIGH": 43.30,
                    "LOW": 39.50,
                    "VOLUME": 282235.0,
                    "AMOUNT": 1179249854.0,
                }
            ]
        ),
    )

    snapshot = provider.get_snapshot("603063", TradeRecord.Market.A_STOCK)

    assert snapshot["latest_price"] == 42.99
    assert snapshot["previous_close"] == 40.70
    assert snapshot["trade_date"] == "20260427"
    assert snapshot["data_source"] == "tushare_realtime_quote_dc"


def test_hk_akshare_provider_maps_hist_rows():
    cache.clear()
    provider = HKAkshareProvider(
        client=FakeAkshare(
            hk_hist_rows=[
                {
                    "日期": "2026-04-23",
                    "开盘": 12.0,
                    "收盘": 12.5,
                    "最高": 12.8,
                    "最低": 11.9,
                    "成交量": 1200000,
                    "成交额": 15000000,
                }
            ]
        )
    )

    bars = provider.fetch_daily_bars("00189", start=date(2026, 4, 1), end=date(2026, 4, 23), market=TradeRecord.Market.HK_STOCK)

    assert bars[0]["trade_date"] == "20260423"
    assert bars[0]["close"] == 12.5
    assert bars[0]["pre_close"] == 12.5


def test_hk_tushare_provider_maps_daily_rows():
    fake_pro = FakePro(
        [
            {
                "ts_code": "00189.HK",
                "trade_date": "20260423",
                "open": 11.71,
                "high": 11.71,
                "low": 11.34,
                "close": 11.38,
                "pre_close": 11.64,
                "vol": 9645821,
                "amount": 110282381.05,
            }
        ]
    )
    provider = HKTushareProvider(token="demo-token", client=fake_pro)

    bars = provider.fetch_daily_bars("00189", start=date(2026, 4, 1), end=date(2026, 4, 23), market=TradeRecord.Market.HK_STOCK)

    assert fake_pro.calls[0]["ts_code"] == "00189.HK"
    assert bars[0]["trade_date"] == "20260423"
    assert bars[0]["close"] == 11.38
    assert bars[0]["pre_close"] == 11.64


def test_hk_akshare_provider_maps_snapshot_rows():
    cache.clear()
    client = FakeAkshare(
        hk_spot_rows=[
            {
                "代码": "00189",
                "最新价": 12.5,
                "昨收": 12.1,
                "今开": 12.0,
                "最高": 12.8,
                "最低": 11.9,
                "成交量": 1200000,
                "成交额": 15000000,
            }
        ]
    )
    provider = HKAkshareProvider(client=client)

    snapshot = provider.get_snapshot("00189", TradeRecord.Market.HK_STOCK)
    snapshot_again = provider.get_snapshot("00189", TradeRecord.Market.HK_STOCK)

    assert snapshot["latest_price"] == 12.5
    assert snapshot["previous_close"] == 12.1
    assert snapshot["data_source"] == "akshare_hk_spot"
    assert snapshot["degraded"] is False
    assert snapshot_again["latest_price"] == 12.5
    assert client.spot_calls == 1


def test_fallback_hk_provider_prefers_akshare_spot_for_normal_hk_snapshot():
    cache.clear()
    tushare_provider = HKTushareProvider(
        token="demo-token",
        client=FakePro(
            [
                {
                    "ts_code": "00189.HK",
                    "trade_date": "20260424",
                    "open": 11.71,
                    "high": 11.71,
                    "low": 11.34,
                    "close": 11.38,
                    "pre_close": 11.64,
                    "vol": 9645821,
                    "amount": 110282381.05,
                }
            ]
        ),
    )
    ak_provider = HKAkshareProvider(
        client=FakeAkshare(
            hk_spot_rows=[
                {
                    "代码": "00189",
                    "最新价": 12.31,
                    "昨收": 12.30,
                    "今开": 12.38,
                    "最高": 12.54,
                    "最低": 12.20,
                    "成交量": 7893000,
                    "成交额": 97526172,
                }
            ]
        )
    )
    provider = FallbackHKProvider(
        providers=[tushare_provider, ak_provider],
        snapshot_providers=[ak_provider, tushare_provider],
    )

    snapshot = provider.get_snapshot("00189", TradeRecord.Market.HK_STOCK)

    assert snapshot["latest_price"] == 12.31
    assert snapshot["data_source"] == "akshare_hk_spot"


def test_hk_akshare_provider_falls_back_to_hist_when_spot_missing():
    cache.clear()
    client = FakeAkshare(
        hk_spot_rows=[],
        hk_hist_rows=[
            {
                "日期": "2026-04-21",
                "开盘": 42.62,
                "收盘": 42.72,
                "最高": 43.14,
                "最低": 41.44,
                "成交量": 48480119,
                "成交额": 2058314863,
            },
            {
                "日期": "2026-04-22",
                "开盘": 41.82,
                "收盘": 43.22,
                "最高": 43.22,
                "最低": 40.74,
                "成交量": 35713010,
                "成交额": 1505707129,
            },
        ],
    )
    provider = HKAkshareProvider(client=client)

    snapshot = provider.get_snapshot("07709", TradeRecord.Market.HK_STOCK)

    assert snapshot["latest_price"] == 43.22
    assert snapshot["previous_close"] == 42.72
    assert snapshot["data_source"] == "akshare_hk_hist"
    assert snapshot["degraded"] is True
    assert client.hist_calls == 1


def test_hk_web_scraper_provider_parses_sina_quote():
    cache.clear()

    def fake_get(url, headers, timeout):
        assert "hq.sinajs.cn" in url
        return FakeResponse(
            'var hq_str_hk07709="XL2CSOPHYNIX,ＸＬ二南方海力士,43.360,43.220,44.000,39.840,42.580,-0.640,-1.481,42.50000,42.50000,3217294210,76121809,0.000,0.000,44.000,8.420,2026/04/23,16:05";'
        )

    provider = HKWebScraperProvider(request_get=fake_get)
    snapshot = provider.get_snapshot("07709", TradeRecord.Market.HK_STOCK)

    assert snapshot["latest_price"] == 42.58
    assert snapshot["previous_close"] == 43.22
    assert snapshot["open"] == 43.36
    assert snapshot["high"] == 44.0
    assert snapshot["low"] == 39.84
    assert snapshot["trade_date"] == "2026-04-23"
    assert snapshot["data_source"] == "sina_hk_quote"
    assert snapshot["degraded"] is True


def test_fallback_hk_provider_uses_web_provider_for_special_etf_when_akshare_empty():
    cache.clear()
    ak_provider = HKAkshareProvider(client=FakeAkshare(hk_spot_rows=[], hk_hist_rows=[]))

    def fake_get(url, headers, timeout):
        return FakeResponse(
            'var hq_str_hk07226="XL2CSOPHSTECH,ＸＬ二南方恒科,3.950,3.944,3.950,3.760,3.780,-0.164,-4.158,3.77800,3.77800,1175576923,309100260,0.000,0.000,7.925,3.430,2026/04/23,16:01";'
        )

    web_provider = HKWebScraperProvider(request_get=fake_get)
    provider = FallbackHKProvider([ak_provider, web_provider])

    snapshot = provider.get_snapshot("07226", TradeRecord.Market.HK_STOCK)

    assert snapshot["latest_price"] == 3.78
    assert snapshot["previous_close"] == 3.944
    assert snapshot["trade_date"] == "2026-04-23"
    assert snapshot["data_source"] == "sina_hk_quote"


def test_fallback_hk_provider_uses_akshare_hist_for_special_etf_daily_bars():
    cache.clear()
    class HistOnlyProvider:
        provider_name = "akshare_hk"

        def fetch_daily_bars(self, stock_code, start, end, market):
            assert stock_code == "07226"
            assert market == TradeRecord.Market.HK_STOCK
            return [
                {
                    "trade_date": "20260504",
                    "open": 3.908,
                    "high": 4.066,
                    "low": 3.898,
                    "close": 3.944,
                    "pre_close": 3.944,
                    "volume": 348899664.0,
                    "amount": 1395304240.0,
                    "data_source": "akshare_hk",
                },
                {
                    "trade_date": "20260505",
                    "open": 3.914,
                    "high": 3.914,
                    "low": 3.752,
                    "close": 3.858,
                    "pre_close": 3.944,
                    "volume": 280735840.0,
                    "amount": 1070312656.0,
                    "data_source": "akshare_hk",
                },
            ]

        def get_snapshot(self, stock_code, market):
            return {}

    ak_provider = HistOnlyProvider()
    web_provider = HKWebScraperProvider(request_get=lambda *args, **kwargs: FakeResponse(""))
    provider = FallbackHKProvider(
        providers=[ak_provider, web_provider],
        etf_codes={"07226"},
        etf_providers=[ak_provider, web_provider],
        snapshot_providers=[web_provider, ak_provider],
        etf_snapshot_providers=[web_provider, ak_provider],
    )

    bars = provider.fetch_daily_bars("07226", start=date(2026, 5, 4), end=date(2026, 5, 5), market=TradeRecord.Market.HK_STOCK)

    assert len(bars) == 2
    assert bars[0]["trade_date"] == "20260504"
    assert bars[1]["trade_date"] == "20260505"
    assert bars[1]["pre_close"] == 3.944


def test_fallback_hk_provider_uses_tushare_then_web_for_special_etf():
    class EmptyProvider:
        provider_name = "empty"

        def __init__(self):
            self.calls = 0

        def fetch_daily_bars(self, stock_code, start, end, market):
            self.calls += 1
            return []

        def get_snapshot(self, stock_code, market):
            self.calls += 1
            return {}

    tushare_provider = EmptyProvider()
    ak_provider = EmptyProvider()

    def fake_get(url, headers, timeout):
        return FakeResponse(
            'var hq_str_hk07709="XL2CSOPHYNIX,ＸＬ二南方海力士,43.360,43.220,44.000,39.840,42.580,-0.640,-1.481,42.50000,42.50000,3217294210,76121809,0.000,0.000,44.000,8.420,2026/04/23,16:05";'
        )

    web_provider = HKWebScraperProvider(request_get=fake_get)
    provider = FallbackHKProvider(
        providers=[tushare_provider, ak_provider, web_provider],
        etf_codes={"07709"},
        etf_providers=[tushare_provider, web_provider],
    )

    snapshot = provider.get_snapshot("07709", TradeRecord.Market.HK_STOCK)

    assert snapshot["latest_price"] == 42.58
    assert snapshot["data_source"] == "sina_hk_quote"
    assert tushare_provider.calls >= 1
    assert ak_provider.calls == 0


def test_fx_akshare_provider_normalizes_hkd_cny_rate():
    cache.clear()
    client = FakeAkshare(
        fx_rows=[
            {
                "日期": "2026-04-23",
                "央行中间价": 91.23,
            }
        ]
    )
    provider = FXAkshareProvider(client=client)

    rate = provider.get_fx_rate("HKD", "CNY", date(2026, 4, 23))
    rate_again = provider.get_fx_rate("HKD", "CNY", date(2026, 4, 23))

    assert rate == 0.9123
    assert rate_again == 0.9123
    assert client.fx_calls == 1
