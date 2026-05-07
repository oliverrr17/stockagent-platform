from __future__ import annotations

from datetime import date, datetime
import os

from django.utils import timezone

from trades.models import TradeRecord


DEFAULT_TRADE_INGESTION_START_DATE = "2026-04-23"


def trade_ingestion_start_date() -> date:
    raw_value = os.getenv("TRADE_INGESTION_START_DATE", DEFAULT_TRADE_INGESTION_START_DATE).strip()
    return date.fromisoformat(raw_value)


def is_trade_before_ingestion_start(record_data: dict) -> bool:
    trade_time = record_data.get("trade_time")
    if trade_time is None:
        return False
    return _normalize_date(trade_time) < trade_ingestion_start_date()


def should_enforce_baseline_for_source(source: str) -> bool:
    return source == TradeRecord.Source.HSBC_EMAIL


def _normalize_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return timezone.localtime(value).date()
    text = str(value).strip()
    if "T" in text:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return timezone.localtime(parsed).date()
    return date.fromisoformat(text)
