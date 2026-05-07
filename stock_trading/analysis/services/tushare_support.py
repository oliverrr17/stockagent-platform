from __future__ import annotations

from datetime import date
import os

from django.core.cache import cache


def normalize_a_share_code(stock_code: str) -> str:
    code = str(stock_code).strip().upper()
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"Unsupported A-share code: {stock_code}")
    if code.startswith(("600", "601", "603", "605", "688", "900")):
        return f"{code}.SH"
    return f"{code}.SZ"


class TushareProAdapter:
    CACHE_TTL_SECONDS = 300

    def __init__(self, token: str | None = None, client=None):
        self.token = (token or os.getenv("TUSHARE_TOKEN", "")).strip()
        self._client = client

    @property
    def is_available(self) -> bool:
        return bool(self.token or self._client)

    def client(self):
        if self._client is not None:
            return self._client
        if not self.token:
            raise ValueError("TUSHARE_TOKEN is not configured.")
        import tushare as ts

        self._client = ts.pro_api(self.token)
        return self._client

    def call(self, method: str, cache_key: str | None = None, **kwargs):
        if cache_key:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        frame = getattr(self.client(), method)(**kwargs)
        if cache_key:
            cache.set(cache_key, frame, timeout=self.CACHE_TTL_SECONDS)
        return frame

    @classmethod
    def date_key(cls, prefix: str, target_date: date, suffix: str = "") -> str:
        return f"{prefix}:{target_date.isoformat()}:{suffix}".rstrip(":")
