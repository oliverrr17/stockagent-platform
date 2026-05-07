from __future__ import annotations

from datetime import date, datetime
import os

from django.core.cache import cache
from django.utils import timezone


TRADING_DAY_CACHE_TTL_SECONDS = 60 * 60 * 12


def is_cn_equity_trading_day(target_date: date | datetime | None = None, token: str | None = None, client=None) -> bool:
    trading_date = _normalize_date(target_date)
    if trading_date.weekday() >= 5:
        return False

    cache_key = f"trading-calendar:sse:{trading_date.isoformat()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)

    token = token if token is not None else os.getenv("TUSHARE_TOKEN", "").strip()
    if client is None and token:
        try:
            import tushare as ts

            client = ts.pro_api(token)
        except Exception:
            client = None

    if client is not None:
        try:
            frame = client.trade_cal(
                exchange="SSE",
                start_date=trading_date.strftime("%Y%m%d"),
                end_date=trading_date.strftime("%Y%m%d"),
            )
            rows = frame.to_dict("records") if frame is not None else []
            if rows:
                is_open = str(rows[0].get("is_open", "0")).strip() in {"1", "True", "true"}
                cache.set(cache_key, is_open, TRADING_DAY_CACHE_TTL_SECONDS)
                return is_open
        except Exception:
            pass

    cache.set(cache_key, True, TRADING_DAY_CACHE_TTL_SECONDS)
    return True


def _normalize_date(value: date | datetime | None) -> date:
    if value is None:
        return timezone.localdate()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value).date()
