from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import os
import re

from django.core.cache import cache

from config.trading_calendar import is_cn_equity_trading_day
from trades.models import TradeRecord


SPECIAL_HK_ETF_CODES = {"07226", "07709", "07747"}


def _normalize_a_share_code(stock_code: str) -> str:
    code = str(stock_code).strip().upper()
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"Unsupported A-share code: {stock_code}")
    if code.startswith(("600", "601", "603", "605", "688", "900")):
        return f"{code}.SH"
    return f"{code}.SZ"


@dataclass
class DailyBar:
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    volume: float
    amount: float

    def as_dict(self) -> dict:
        return {
            "trade_date": self.trade_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "pre_close": self.pre_close,
            "volume": self.volume,
            "amount": self.amount,
        }


class AShareTushareProvider:
    provider_name = "tushare_daily"

    def __init__(self, token: str, client=None, realtime_quote_fetcher=None):
        if not token:
            raise ValueError("TUSHARE_TOKEN is required for Tushare provider.")
        self.token = token
        self.client = client or self._build_client(token)
        self.realtime_quote_fetcher = realtime_quote_fetcher or self._build_realtime_quote_fetcher(token)

    def _build_client(self, token: str):
        import tushare as ts

        return ts.pro_api(token)

    def _build_realtime_quote_fetcher(self, token: str):
        import tushare as ts

        ts.set_token(token)
        return ts.realtime_quote

    def fetch_daily_bars(self, stock_code: str, start: date, end: date, market: str):
        if market != TradeRecord.Market.A_STOCK:
            raise ValueError("AShareTushareProvider only supports A-share market.")

        frame = self.client.daily(
            ts_code=_normalize_a_share_code(stock_code),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        rows = frame.to_dict("records") if frame is not None else []
        bars = [
            DailyBar(
                trade_date=str(row["trade_date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                pre_close=float(row.get("pre_close") or row["close"]),
                volume=float(row.get("vol") or row.get("volume") or 0),
                amount=float(row.get("amount") or 0),
            ).as_dict()
            for row in rows
        ]
        for bar in bars:
            bar["data_source"] = self.provider_name
        bars.sort(key=lambda item: item["trade_date"])
        return bars

    def get_snapshot(self, stock_code: str, market: str):
        realtime_snapshot = self._get_realtime_snapshot(stock_code, market)
        if realtime_snapshot:
            return realtime_snapshot

        bars = self.fetch_daily_bars(stock_code, start=date.today() - timedelta(days=10), end=date.today(), market=market)
        if not bars:
            return {}
        latest = bars[-1]
        previous_close = latest.get("pre_close") or (bars[-2]["close"] if len(bars) > 1 else latest["close"])
        return {
            "latest_price": latest["close"],
            "previous_close": previous_close,
            "trade_date": latest["trade_date"],
            "data_source": self.provider_name,
            "degraded": False,
            "degraded_reason": "",
        }

    def _get_realtime_snapshot(self, stock_code: str, market: str):
        if market != TradeRecord.Market.A_STOCK or not is_cn_equity_trading_day(date.today()):
            return {}
        if self.realtime_quote_fetcher is None:
            return {}

        for source in ("dc", "sina"):
            try:
                frame = self.realtime_quote_fetcher(ts_code=_normalize_a_share_code(stock_code), src=source)
            except Exception:
                continue
            rows = frame.to_dict("records") if frame is not None else []
            if not rows:
                continue

            row = rows[0]
            latest_price = row.get("PRICE")
            previous_close = row.get("PRE_CLOSE")
            trade_date = str(row.get("DATE", "")).strip()
            if latest_price in (None, "") or previous_close in (None, "") or not trade_date:
                continue

            return {
                "latest_price": float(latest_price),
                "previous_close": float(previous_close),
                "trade_date": trade_date,
                "open": float(row.get("OPEN") or latest_price),
                "high": float(row.get("HIGH") or latest_price),
                "low": float(row.get("LOW") or latest_price),
                "volume": float(row.get("VOLUME") or 0),
                "amount": float(row.get("AMOUNT") or 0),
                "data_source": f"tushare_realtime_quote_{source}",
                "degraded": False,
                "degraded_reason": "",
            }
        return {}


class HKTushareProvider:
    provider_name = "tushare_hk_daily"

    def __init__(self, token: str, client=None):
        if not token:
            raise ValueError("TUSHARE_TOKEN is required for HK Tushare provider.")
        self.token = token
        self.client = client or self._build_client(token)

    def _build_client(self, token: str):
        import tushare as ts

        return ts.pro_api(token)

    def fetch_daily_bars(self, stock_code: str, start: date, end: date, market: str):
        if market != TradeRecord.Market.HK_STOCK:
            raise ValueError("HKTushareProvider only supports HK market.")

        frame = self.client.hk_daily(
            ts_code=f"{str(stock_code).strip().upper()}.HK",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        rows = frame.to_dict("records") if frame is not None else []
        bars = [
            DailyBar(
                trade_date=str(row["trade_date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                pre_close=float(row.get("pre_close") or row["close"]),
                volume=float(row.get("vol") or row.get("volume") or 0),
                amount=float(row.get("amount") or 0),
            ).as_dict()
            for row in rows
        ]
        for bar in bars:
            bar["data_source"] = self.provider_name
        bars.sort(key=lambda item: item["trade_date"])
        return bars

    def get_snapshot(self, stock_code: str, market: str):
        bars = self.fetch_daily_bars(stock_code, start=date.today() - timedelta(days=10), end=date.today(), market=market)
        if not bars:
            return {}
        latest = bars[-1]
        previous_close = latest.get("pre_close") or (bars[-2]["close"] if len(bars) > 1 else latest["close"])
        return {
            "latest_price": latest["close"],
            "previous_close": previous_close,
            "trade_date": latest["trade_date"],
            "data_source": self.provider_name,
            "degraded": False,
            "degraded_reason": "",
        }


class HKAkshareProvider:
    provider_name = "akshare_hk"
    CACHE_TTL_SECONDS = 300

    def __init__(self, client=None):
        self.client = client or self._build_client()

    def _build_client(self):
        import akshare as ak

        return ak

    def fetch_daily_bars(self, stock_code: str, start: date, end: date, market: str):
        if market != TradeRecord.Market.HK_STOCK:
            raise ValueError("HKAkshareProvider only supports HK market.")

        cache_key = self._hist_cache_key(stock_code, start, end)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        frame = self._quiet_call(
            self.client.stock_hk_hist,
            symbol=str(stock_code).strip().upper(),
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="",
        )
        rows = frame.to_dict("records") if frame is not None else []
        bars = [
            DailyBar(
                trade_date=self._normalize_trade_date(row["日期"]),
                open=float(row["开盘"]),
                high=float(row["最高"]),
                low=float(row["最低"]),
                close=float(row["收盘"]),
                pre_close=float(row.get("昨收") or row.get("前收盘") or row["收盘"]),
                volume=float(row.get("成交量") or 0),
                amount=float(row.get("成交额") or 0),
            ).as_dict()
            for row in rows
        ]
        for bar in bars:
            bar["data_source"] = self.provider_name
        bars.sort(key=lambda item: item["trade_date"])
        if len(bars) > 1:
            for index in range(1, len(bars)):
                bars[index]["pre_close"] = bars[index - 1]["close"]
        cache.set(cache_key, bars, timeout=self.CACHE_TTL_SECONDS)
        return bars

    def get_snapshot(self, stock_code: str, market: str):
        if market != TradeRecord.Market.HK_STOCK:
            raise ValueError("HKAkshareProvider only supports HK market.")

        stock_code = str(stock_code).strip().upper()
        try:
            snapshots = self._load_spot_snapshot_cache()
        except Exception:
            snapshots = {}

        cached = snapshots.get(stock_code)
        if cached:
            return cached

        try:
            bars = self.fetch_daily_bars(
                stock_code=stock_code,
                start=date.today() - timedelta(days=10),
                end=date.today(),
                market=market,
            )
        except Exception:
            bars = []

        if not bars:
            return {}

        latest = bars[-1]
        previous_close = latest.get("pre_close") or (bars[-2]["close"] if len(bars) > 1 else latest["close"])
        return {
            "latest_price": latest["close"],
            "previous_close": previous_close,
            "trade_date": latest["trade_date"],
            "open": latest["open"],
            "high": latest["high"],
            "low": latest["low"],
            "volume": latest["volume"],
            "amount": latest["amount"],
            "data_source": "akshare_hk_hist",
            "degraded": True,
            "degraded_reason": "港股实时行情不可用，当前使用最近可用日线收盘价。",
        }

    def _normalize_trade_date(self, value):
        text = str(value).strip()
        if "-" in text:
            return text.replace("-", "")
        return text

    def _quiet_call(self, func, *args, **kwargs):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return func(*args, **kwargs)

    def _load_spot_snapshot_cache(self):
        cache_key = "akshare:hk:spot_snapshot"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        frame = self._quiet_call(self.client.stock_hk_spot)
        rows = frame.to_dict("records") if frame is not None else []
        snapshot_cache = {}
        for row in rows:
            stock_code = str(row.get("代码", "")).strip().upper()
            if not stock_code:
                continue
            snapshot_cache[stock_code] = {
                "latest_price": float(row["最新价"]),
                "previous_close": float(row.get("昨收") or row["最新价"]),
                "open": float(row.get("今开") or row["最新价"]),
                "high": float(row.get("最高") or row["最新价"]),
                "low": float(row.get("最低") or row["最新价"]),
                "volume": float(row.get("成交量") or 0),
                "amount": float(row.get("成交额") or 0),
                "data_source": "akshare_hk_spot",
                "degraded": False,
                "degraded_reason": "",
            }
        cache.set(cache_key, snapshot_cache, timeout=self.CACHE_TTL_SECONDS)
        return snapshot_cache

    def _hist_cache_key(self, stock_code: str, start: date, end: date):
        return f"akshare:hk:hist:{stock_code}:{start.isoformat()}:{end.isoformat()}"


class HKWebScraperProvider:
    provider_name = "hk_web_quote"
    CACHE_TTL_SECONDS = 1800
    SUPPORTED_CODES = {"07226", "07709", "07747"}

    def __init__(self, request_get=None):
        if request_get is None:
            import requests

            request_get = requests.get
        self.request_get = request_get

    def fetch_daily_bars(self, stock_code: str, start: date, end: date, market: str):
        return []

    def get_snapshot(self, stock_code: str, market: str):
        if market != TradeRecord.Market.HK_STOCK:
            raise ValueError("HKWebScraperProvider only supports HK market.")

        stock_code = str(stock_code).strip().upper()
        if stock_code not in self.SUPPORTED_CODES:
            return {}

        cache_key = f"hk:web:snapshot:{stock_code}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        snapshot = self._fetch_sina_snapshot(stock_code)
        cache.set(cache_key, snapshot, timeout=self.CACHE_TTL_SECONDS)
        return snapshot

    def _fetch_sina_snapshot(self, stock_code: str):
        response = self.request_get(
            f"https://hq.sinajs.cn/list=hk{stock_code}",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": f"https://stock.finance.sina.com.cn/hkstock/quotes/{stock_code}.html",
            },
            timeout=15,
        )
        response.raise_for_status()
        text = response.text
        match = re.search(rf'var\s+hq_str_hk{re.escape(stock_code)}="([^"]+)"', text)
        if not match:
            return {}

        fields = match.group(1).split(",")
        if len(fields) < 13:
            return {}

        latest_price = self._to_float(fields[6])
        previous_close = self._to_float(fields[3])
        open_price = self._to_float(fields[2])
        high_price = self._to_float(fields[4])
        low_price = self._to_float(fields[5])
        amount = self._to_float(fields[11])
        volume = self._to_float(fields[12])

        if latest_price is None or previous_close is None:
            return {}

        return {
            "latest_price": latest_price,
            "previous_close": previous_close,
            "trade_date": fields[17].replace("/", "-") if len(fields) > 17 and fields[17].strip() else date.today().isoformat(),
            "open": open_price or latest_price,
            "high": high_price or latest_price,
            "low": low_price or latest_price,
            "volume": volume or 0.0,
            "amount": amount or 0.0,
            "data_source": "sina_hk_quote",
            "degraded": True,
            "degraded_reason": "港股网页行情抓取成功，当前使用低频网页报价。",
        }

    def _to_float(self, value):
        text = str(value).strip()
        if not text or text == "--":
            return None
        try:
            return float(text)
        except ValueError:
            return None


class FallbackHKProvider:
    provider_name = "hk_fallback_chain"

    def __init__(
        self,
        providers: list,
        etf_codes: set[str] | None = None,
        etf_providers: list | None = None,
        snapshot_providers: list | None = None,
        etf_snapshot_providers: list | None = None,
    ):
        self.providers = providers
        self.etf_codes = {code.strip().upper() for code in (etf_codes or set())}
        self.etf_providers = etf_providers or providers
        self.snapshot_providers = snapshot_providers or providers
        self.etf_snapshot_providers = etf_snapshot_providers or self.etf_providers

    def _providers_for_code(self, stock_code: str):
        if str(stock_code).strip().upper() in self.etf_codes:
            return self.etf_providers
        return self.providers

    def _snapshot_providers_for_code(self, stock_code: str):
        if str(stock_code).strip().upper() in self.etf_codes:
            return self.etf_snapshot_providers
        return self.snapshot_providers

    def fetch_daily_bars(self, stock_code: str, start: date, end: date, market: str):
        for provider in self._providers_for_code(stock_code):
            try:
                bars = provider.fetch_daily_bars(stock_code, start=start, end=end, market=market)
            except Exception:
                bars = []
            if bars:
                return bars
        return []

    def get_snapshot(self, stock_code: str, market: str):
        for provider in self._snapshot_providers_for_code(stock_code):
            try:
                snapshot = provider.get_snapshot(stock_code, market)
            except Exception:
                snapshot = {}
            if snapshot and snapshot.get("latest_price") is not None:
                return snapshot
        return {}


class FXAkshareProvider:
    provider_name = "akshare_boc_fx"
    CACHE_TTL_SECONDS = 300

    def __init__(self, client=None):
        self.client = client or self._build_client()

    def _build_client(self):
        import akshare as ak

        return ak

    def get_fx_rate(self, base_currency: str, quote_currency: str, rate_date: date):
        if (base_currency, quote_currency) != ("HKD", "CNY"):
            raise ValueError(f"Unsupported FX pair: {base_currency}/{quote_currency}")

        cache_key = f"akshare:fx:{base_currency}:{quote_currency}:{rate_date.isoformat()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        frame = self._quiet_call(
            self.client.currency_boc_sina,
            symbol="港币",
            start_date=rate_date.strftime("%Y%m%d"),
            end_date=rate_date.strftime("%Y%m%d"),
        )
        rows = frame.to_dict("records") if frame is not None else []
        if not rows:
            raise ValueError(f"No HKD/CNY FX rate returned for {rate_date}")

        row = rows[-1]
        raw_value = row.get("央行中间价") or row.get("中行折算价")
        if raw_value is None:
            raise ValueError(f"Unsupported FX row shape for {rate_date}")
        rate = float((Decimal(str(raw_value)) / Decimal("100")).quantize(Decimal("0.0001")))
        cache.set(cache_key, rate, timeout=self.CACHE_TTL_SECONDS)
        return rate

    def _quiet_call(self, func, *args, **kwargs):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return func(*args, **kwargs)


class CompositeMarketDataProvider:
    provider_name = "composite_market_data"

    def __init__(self, a_share_provider=None, hk_provider=None, fx_provider=None):
        self.a_share_provider = a_share_provider
        self.hk_provider = hk_provider
        self.fx_provider = fx_provider

    def fetch_daily_bars(self, stock_code: str, start: date, end: date, market: str):
        provider = self._select_market_provider(market)
        if provider is None:
            return []
        return provider.fetch_daily_bars(stock_code, start=start, end=end, market=market)

    def get_snapshot(self, stock_code: str, market: str):
        provider = self._select_market_provider(market)
        if provider is None or not hasattr(provider, "get_snapshot"):
            return {}
        return provider.get_snapshot(stock_code, market)

    def get_fx_rate(self, base_currency: str, quote_currency: str, rate_date: date):
        if base_currency == quote_currency:
            return 1.0
        if self.fx_provider is None:
            raise ValueError(f"FX provider is not configured for {base_currency}/{quote_currency}")
        return self.fx_provider.get_fx_rate(base_currency, quote_currency, rate_date)

    def _select_market_provider(self, market: str):
        if market == TradeRecord.Market.A_STOCK:
            return self.a_share_provider
        if market == TradeRecord.Market.HK_STOCK:
            return self.hk_provider
        return None


def build_market_data_provider():
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    a_share_provider = AShareTushareProvider(token=token) if token else None
    try:
        hk_tushare_provider = HKTushareProvider(token=token) if token else None
        hk_web_provider = HKWebScraperProvider()
        hk_akshare_provider = HKAkshareProvider()
        default_hk_providers = [provider for provider in (hk_tushare_provider, hk_akshare_provider, hk_web_provider) if provider is not None]
        etf_hk_providers = [provider for provider in (hk_tushare_provider, hk_akshare_provider, hk_web_provider) if provider is not None]
        default_hk_snapshot_providers = [provider for provider in (hk_akshare_provider, hk_web_provider, hk_tushare_provider) if provider is not None]
        etf_hk_snapshot_providers = [provider for provider in (hk_web_provider, hk_tushare_provider) if provider is not None]
        hk_provider = FallbackHKProvider(
            default_hk_providers,
            etf_codes=SPECIAL_HK_ETF_CODES,
            etf_providers=etf_hk_providers,
            snapshot_providers=default_hk_snapshot_providers,
            etf_snapshot_providers=etf_hk_snapshot_providers,
        )
        fx_provider = FXAkshareProvider()
    except Exception:
        hk_provider = None
        fx_provider = None
    if not any((a_share_provider, hk_provider, fx_provider)):
        return None
    return CompositeMarketDataProvider(
        a_share_provider=a_share_provider,
        hk_provider=hk_provider,
        fx_provider=fx_provider,
    )


def trade_date_window(trade_time, lookback_days: int):
    trade_dt = _coerce_datetime(trade_time)
    trade_day = trade_dt.date()
    return trade_day - timedelta(days=lookback_days), trade_day


def _coerce_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
