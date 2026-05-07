from rest_framework import serializers

from .models import ReviewReport
from trades.serializers import TradeIntentSnapshotSerializer


_MISSING_DATA_NOTE_LABELS = {
    "intent_snapshot_missing": "交易意图快照缺失，无法对比计划与实际执行。",
    "review_llm_not_configured": "LLM 尚未配置，当前报告为本地降级版。",
}


def _normalize_missing_data_notes(value):
    if not value:
        return []

    def normalize_item(item):
        text = str(item or "").strip()
        return _MISSING_DATA_NOTE_LABELS.get(text, text)

    if isinstance(value, str):
        text = normalize_item(value)
        return [text] if text else []

    if not isinstance(value, list):
        text = normalize_item(value)
        return [text] if text else []

    items = [normalize_item(item) for item in value if str(item or "").strip()]
    if not items:
        return []

    short_count = sum(1 for item in items if len(item) <= 2)
    compact_token_count = sum(1 for item in items if item.replace("_", "").replace("-", "").replace(".", "").replace(":", "").isalnum())
    if len(items) >= 6 and (short_count >= len(items) - 1 or compact_token_count >= 5):
        return ["".join(items)]

    return items


class ReviewReportSerializer(serializers.ModelSerializer):
    trade_summary = serializers.SerializerMethodField()
    trade_intent_snapshot = serializers.SerializerMethodField()

    class Meta:
        model = ReviewReport
        fields = "__all__"

    def get_trade_summary(self, obj):
        trade = obj.trade_record
        return {
            "id": trade.id,
            "stock_code": trade.stock_code,
            "stock_name": trade.stock_name,
            "market": trade.market,
            "direction": trade.direction,
            "price": str(trade.price),
            "quantity": trade.quantity,
            "trade_time": trade.trade_time,
            "source": trade.source,
        }

    def get_trade_intent_snapshot(self, obj):
        try:
            snapshot = obj.trade_record.intent_snapshot
        except Exception:
            return None
        return TradeIntentSnapshotSerializer(snapshot).data

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if data.get("intent_snapshot") == {}:
            data["intent_snapshot"] = None

        coach_payload = data.get("coach_report_payload")
        if isinstance(coach_payload, dict):
            coach_payload["missing_data_notes"] = _normalize_missing_data_notes(coach_payload.get("missing_data_notes"))

        return data
