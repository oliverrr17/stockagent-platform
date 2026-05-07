from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from analysis.services.market_data import build_market_data_provider
from analysis.services.market_data import SPECIAL_HK_ETF_CODES
from portfolio.models import Position, PositionEntry, SecurityPriceSnapshot
from trades.models import TradeRecord


def _to_decimal(value):
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _snapshot_trade_date(snapshot: dict | None) -> date | None:
    if not snapshot:
        return None

    raw_value = snapshot.get("trade_date")
    if not raw_value:
        return None

    text = str(raw_value).strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text)


class MarketSnapshotService:
    LOOKBACK_DAYS = 10

    def __init__(self, market_data_provider=None):
        self.market_data_provider = market_data_provider or build_market_data_provider()

    def tracked_securities(self):
        result: dict[tuple[str, str], dict] = {}

        def remember(stock_code: str, market: str, stock_name: str):
            key = (str(stock_code).strip().upper(), market)
            if key not in result:
                result[key] = {
                    "stock_code": key[0],
                    "market": market,
                    "stock_name": str(stock_name or "").strip(),
                }
            elif stock_name and not result[key]["stock_name"]:
                result[key]["stock_name"] = str(stock_name).strip()

        for position in Position.objects.all():
            remember(position.stock_code, position.market, position.stock_name)
        for entry in PositionEntry.objects.all():
            remember(entry.stock_code, entry.market, entry.stock_name)
        for trade in TradeRecord.objects.all():
            remember(trade.stock_code, trade.market, trade.stock_name)

        return sorted(result.values(), key=lambda item: (item["market"], item["stock_code"]))

    def refresh_snapshots(self, end_date: date | None = None):
        if self.market_data_provider is None:
            return {"securities": 0, "snapshots_written": 0}

        target_date = end_date or timezone.localdate()
        snapshots_written = 0
        securities = self.tracked_securities()
        for security in securities:
            snapshots_written += self._refresh_security(
                stock_code=security["stock_code"],
                stock_name=security["stock_name"],
                market=security["market"],
                end_date=target_date,
            )
        return {"securities": len(securities), "snapshots_written": snapshots_written}

    def _refresh_security(self, stock_code: str, stock_name: str, market: str, end_date: date):
        written = 0
        try:
            bars = self.market_data_provider.fetch_daily_bars(
                stock_code,
                start=end_date - timedelta(days=self.LOOKBACK_DAYS),
                end=end_date,
                market=market,
            )
        except Exception:
            bars = []

        if bars:
            for bar in bars:
                written += self._upsert_bar(stock_code, stock_name, market, bar)
            if str(stock_code).strip().upper() not in SPECIAL_HK_ETF_CODES:
                return written

        try:
            snapshot = self.market_data_provider.get_snapshot(stock_code, market)
        except Exception:
            snapshot = {}

        snapshot_date = _snapshot_trade_date(snapshot)
        if snapshot and snapshot_date is not None and snapshot_date == end_date:
            written += self._upsert_snapshot(stock_code, stock_name, market, snapshot, snapshot_date)
        return written

    def _upsert_bar(self, stock_code: str, stock_name: str, market: str, bar: dict):
        trade_date = _snapshot_trade_date({"trade_date": bar.get("trade_date")})
        if trade_date is None:
            return 0
        _, created = SecurityPriceSnapshot.objects.update_or_create(
            stock_code=stock_code,
            market=market,
            trade_date=trade_date,
            defaults={
                "stock_name": stock_name,
                "close_price": _to_decimal(bar.get("close")),
                "previous_close": _to_decimal(bar.get("pre_close") or bar.get("close")),
                "open_price": _to_decimal(bar.get("open")),
                "high_price": _to_decimal(bar.get("high")),
                "low_price": _to_decimal(bar.get("low")),
                "volume": _to_decimal(bar.get("volume")),
                "amount": _to_decimal(bar.get("amount")),
                "source": getattr(self.market_data_provider, "provider_name", "market_data_provider"),
                "degraded": False,
                "degraded_reason": "",
            },
        )
        return 1 if created else 0

    def _upsert_snapshot(self, stock_code: str, stock_name: str, market: str, snapshot: dict, trade_date: date):
        _, created = SecurityPriceSnapshot.objects.update_or_create(
            stock_code=stock_code,
            market=market,
            trade_date=trade_date,
            defaults={
                "stock_name": stock_name,
                "close_price": _to_decimal(snapshot.get("latest_price")),
                "previous_close": _to_decimal(snapshot.get("previous_close") or snapshot.get("latest_price")),
                "open_price": _to_decimal(snapshot.get("open")),
                "high_price": _to_decimal(snapshot.get("high")),
                "low_price": _to_decimal(snapshot.get("low")),
                "volume": _to_decimal(snapshot.get("volume")),
                "amount": _to_decimal(snapshot.get("amount")),
                "source": str(snapshot.get("data_source") or getattr(self.market_data_provider, "provider_name", "market_data_provider")),
                "degraded": bool(snapshot.get("degraded", False)),
                "degraded_reason": str(snapshot.get("degraded_reason") or ""),
            },
        )
        return 1 if created else 0
