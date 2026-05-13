from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from trades.ingestion_policy import (
    is_trade_before_ingestion_start,
    should_enforce_baseline_for_source,
    trade_ingestion_start_date,
)
from trades.models import TradeIntentSnapshot, TradeRecord


class TradeRecorder:
    UNIQUE_FIELDS = ("stock_code", "trade_time", "direction", "quantity", "price")

    def record_trade(self, record_data: dict):
        intent_data = record_data.get("intent_snapshot")
        normalized = self._normalize_record_data(record_data)
        existing = self._find_existing_trade(normalized)
        if existing is not None:
            if intent_data:
                self.sync_intent_snapshot(existing, intent_data)
            return existing, False

        with transaction.atomic():
            trade = TradeRecord.objects.create(**normalized)
            if intent_data:
                self.sync_intent_snapshot(trade, intent_data)
            from portfolio.services.portfolio_manager import PortfolioManager

            PortfolioManager().apply_trade(trade)
        return trade, True

    def is_duplicate(self, record_data: dict) -> bool:
        normalized = self._normalize_record_data(record_data)
        return self._find_existing_trade(normalized) is not None

    @staticmethod
    def get_trades(filters: dict):
        queryset = TradeRecord.objects.all()
        allowed_filters = {
            "market",
            "direction",
            "stock_code",
            "source",
            "stock_name__icontains",
            "trade_time__date",
            "trade_time__gte",
            "trade_time__lte",
        }
        for key, value in filters.items():
            if key in allowed_filters and value is not None:
                queryset = queryset.filter(**{key: value})
        return queryset

    def _unique_lookup(self, record_data: dict) -> dict:
        return {field: record_data[field] for field in self.UNIQUE_FIELDS}

    def _find_existing_trade(self, record_data: dict):
        source = str(record_data.get("source", "")).strip()
        external_trade_id = str(record_data.get("external_trade_id", "")).strip()
        if source == TradeRecord.Source.FUTU_API and external_trade_id:
            return (
                TradeRecord.objects.filter(
                    source=TradeRecord.Source.FUTU_API,
                    external_trade_id=external_trade_id,
                )
                .order_by("-id")
                .first()
            )

        return TradeRecord.objects.filter(**self._unique_lookup(record_data)).order_by("-id").first()

    def _normalize_record_data(self, record_data: dict) -> dict:
        normalized = dict(record_data)
        normalized.pop("intent_snapshot", None)
        normalized["stock_code"] = str(normalized["stock_code"]).strip().upper()
        normalized["stock_name"] = str(normalized["stock_name"]).strip()
        normalized["price"] = self._to_decimal(normalized["price"])
        normalized["commission"] = self._to_decimal(normalized.get("commission", 0))
        normalized["stamp_duty"] = self._to_decimal(normalized.get("stamp_duty", 0))
        normalized["other_fees"] = self._to_decimal(normalized.get("other_fees", 0))
        normalized["quantity"] = int(normalized["quantity"])
        normalized["trade_time"] = self._to_datetime(normalized["trade_time"])
        normalized["external_trade_id"] = str(normalized.get("external_trade_id", "")).strip()
        normalized["fee_details"] = list(normalized.get("fee_details") or [])
        if should_enforce_baseline_for_source(str(normalized.get("source", ""))) and is_trade_before_ingestion_start(normalized):
            raise ValueError(
                f"Trade time before ingestion baseline date {trade_ingestion_start_date().isoformat()}: "
                f"{normalized['trade_time'].isoformat()}"
            )
        return normalized

    def sync_intent_snapshot(self, trade: TradeRecord, intent_data: dict):
        snapshot, _ = TradeIntentSnapshot.objects.get_or_create(trade_record=trade)
        for field, value in intent_data.items():
            if field.endswith("_value") and value in ("", None):
                value = None
            elif field.endswith("_value"):
                value = self._to_decimal(value)
            setattr(snapshot, field, value)
        snapshot.save()
        return snapshot

    def _to_decimal(self, value) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _to_datetime(self, value):
        if hasattr(value, "tzinfo"):
            if timezone.is_naive(value):
                return timezone.make_aware(value, timezone.get_current_timezone())
            return value

        parsed = parse_datetime(str(value))
        if parsed is None:
            raise ValueError(f"Invalid trade_time value: {value}")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
