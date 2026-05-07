from decimal import Decimal

from rest_framework import serializers

from .intent_catalog import (
    EXECUTION_EMOTION_TAGS,
    INTENT_TAG_CHOICES,
    MARKET_CONTEXT_TAGS,
    PLANNED_HOLDING_PERIODS,
    PLANNED_STOP_LOSS_TYPES,
    PLANNED_TAKE_PROFIT_TYPES,
    SECURITY_QUALITY_TAGS,
    SETUP_TAGS,
)
from .models import TradeIntentSnapshot, TradeRecord


class TradeIntentSnapshotSerializer(serializers.ModelSerializer):
    setup_tags = serializers.ListField(
        child=serializers.ChoiceField(choices=SETUP_TAGS),
        required=False,
        allow_empty=True,
    )
    market_context_tags = serializers.ListField(
        child=serializers.ChoiceField(choices=MARKET_CONTEXT_TAGS),
        required=False,
        allow_empty=True,
    )
    security_quality_tags = serializers.ListField(
        child=serializers.ChoiceField(choices=SECURITY_QUALITY_TAGS),
        required=False,
        allow_empty=True,
    )
    execution_emotion_tags = serializers.ListField(
        child=serializers.ChoiceField(choices=EXECUTION_EMOTION_TAGS),
        required=False,
        allow_empty=True,
    )
    planned_holding_period = serializers.ChoiceField(
        choices=PLANNED_HOLDING_PERIODS,
        required=False,
        allow_blank=True,
    )
    planned_stop_loss_type = serializers.ChoiceField(
        choices=PLANNED_STOP_LOSS_TYPES,
        required=False,
        allow_blank=True,
    )
    planned_take_profit_type = serializers.ChoiceField(
        choices=PLANNED_TAKE_PROFIT_TYPES,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = TradeIntentSnapshot
        exclude = ("trade_record",)

    def validate(self, attrs):
        for field_name, allowed_values in INTENT_TAG_CHOICES.items():
            values = list(dict.fromkeys(attrs.get(field_name, [])))
            if any(value not in allowed_values for value in values):
                raise serializers.ValidationError({field_name: "Contains unsupported tag value."})
            attrs[field_name] = values
        if "overall_notes" in attrs:
            attrs["overall_notes"] = str(attrs["overall_notes"] or "").strip()
        return attrs


class TradeRecordSerializer(serializers.ModelSerializer):
    intent_snapshot = TradeIntentSnapshotSerializer(required=False, allow_null=True)

    class Meta:
        model = TradeRecord
        fields = "__all__"

    def update(self, instance, validated_data):
        intent_data = validated_data.pop("intent_snapshot", serializers.empty)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if intent_data is not serializers.empty:
            snapshot, _ = TradeIntentSnapshot.objects.get_or_create(trade_record=instance)
            for field, value in intent_data.items():
                setattr(snapshot, field, self._normalize_optional_decimal(field, value))
            snapshot.save()

        return instance

    def to_representation(self, instance):
        payload = super().to_representation(instance)
        try:
            snapshot = instance.intent_snapshot
        except TradeIntentSnapshot.DoesNotExist:
            payload["intent_snapshot"] = None
        else:
            payload["intent_snapshot"] = TradeIntentSnapshotSerializer(snapshot).data
        return payload

    @staticmethod
    def _normalize_optional_decimal(field_name, value):
        if field_name.endswith("_value") and value in ("", None):
            return None
        if field_name.endswith("_value") and not isinstance(value, Decimal):
            return Decimal(str(value))
        return value
