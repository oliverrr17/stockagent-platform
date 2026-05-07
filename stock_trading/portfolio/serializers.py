from rest_framework import serializers

from .models import CashAccount, CashFlow, FXRate, Position, PositionEntry


class PositionSerializer(serializers.ModelSerializer):
    origin = serializers.SerializerMethodField()
    manual_entry_count = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = "__all__"

    def get_origin(self, obj):
        count = PositionEntry.objects.filter(stock_code=obj.stock_code, market=obj.market).count()
        return "MANUAL" if count > 0 else "SYNCED"

    def get_manual_entry_count(self, obj):
        return PositionEntry.objects.filter(stock_code=obj.stock_code, market=obj.market).count()


class PositionEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PositionEntry
        fields = "__all__"


class HKStockStatsSerializer(serializers.Serializer):
    stock_code = serializers.CharField()
    stock_name = serializers.CharField()
    weighted_avg_cost = serializers.DecimalField(max_digits=12, decimal_places=4)
    quantity = serializers.IntegerField()
    market_value = serializers.DecimalField(max_digits=18, decimal_places=4)
    unrealized_pnl = serializers.DecimalField(max_digits=18, decimal_places=4)
    unrealized_pnl_pct = serializers.DecimalField(max_digits=18, decimal_places=4)
    realized_pnl = serializers.DecimalField(max_digits=18, decimal_places=4)
    daily_pnl = serializers.DecimalField(max_digits=18, decimal_places=4)


class CashAccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = CashAccount
        fields = ["id", "currency", "label", "balance", "created_at", "updated_at"]

    def get_balance(self, obj):
        total = 0
        for flow in obj.flows.all():
            sign = -1 if flow.direction == CashFlow.Direction.WITHDRAWAL else 1
            total += sign * float(flow.amount)
        return total


class CashFlowSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source="cash_account.currency", read_only=True)

    class Meta:
        model = CashFlow
        fields = ["id", "cash_account", "currency", "direction", "amount", "occurred_at", "note", "created_at"]


class FXRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FXRate
        fields = "__all__"


class PortfolioOverviewSerializer(serializers.Serializer):
    base_currency = serializers.CharField()
    start_date = serializers.DateField()
    valuation_date = serializers.DateField()
    audit_status = serializers.CharField()
    cash_balances = serializers.JSONField()
    positions_market_value_cny = serializers.FloatField()
    total_assets_cny = serializers.FloatField()
    realized_pnl_cny = serializers.FloatField()
    unrealized_pnl_cny = serializers.FloatField()
    total_return_cny = serializers.FloatField()
    returns = serializers.JSONField()
    curves = serializers.JSONField()


class PositionDailyContributionSnapshotSerializer(serializers.Serializer):
    stock_code = serializers.CharField()
    stock_name = serializers.CharField()
    market = serializers.CharField()
    start_quantity = serializers.IntegerField()
    end_quantity = serializers.IntegerField()
    previous_close = serializers.FloatField()
    latest_price = serializers.FloatField()
    trade_cash_delta = serializers.FloatField()
    daily_pnl_native = serializers.FloatField()
    daily_pnl_cny = serializers.FloatField()
    fx_rate = serializers.FloatField()
    price_source = serializers.CharField()
    source_trade_date = serializers.DateField(allow_null=True)
    degraded = serializers.BooleanField()
    degraded_reason = serializers.CharField(allow_blank=True)
    audit_status = serializers.CharField()


class PortfolioDailyContributionResponseSerializer(serializers.Serializer):
    snapshot_date = serializers.DateField()
    audit_status = serializers.CharField()
    external_flow_cny = serializers.FloatField()
    computed_daily_pnl_cny = serializers.FloatField()
    contributions = PositionDailyContributionSnapshotSerializer(many=True)


class PositionAnalyticsSerializer(serializers.Serializer):
    stock_code = serializers.CharField()
    stock_name = serializers.CharField()
    market = serializers.CharField()
    quantity = serializers.IntegerField()
    latest_price = serializers.FloatField()
    previous_close = serializers.FloatField()
    cost_basis_native = serializers.FloatField()
    market_value_native = serializers.FloatField()
    market_value_cny = serializers.FloatField()
    unrealized_pnl_native = serializers.FloatField()
    unrealized_pnl_cny = serializers.FloatField()
    daily_pnl_native = serializers.FloatField()
    daily_pnl_cny = serializers.FloatField()
    return_pct = serializers.FloatField()
    currency = serializers.CharField()
    fx_rate = serializers.FloatField()
    data_source = serializers.CharField()
    degraded = serializers.BooleanField()
    degraded_reason = serializers.CharField(allow_blank=True)


class ClearedPositionSerializer(serializers.Serializer):
    stock_code = serializers.CharField()
    stock_name = serializers.CharField()
    market = serializers.CharField()
    quantity = serializers.IntegerField()
    status = serializers.CharField()
    realized_pnl_native = serializers.FloatField()
    realized_pnl_cny = serializers.FloatField()
    updated_at = serializers.DateTimeField()
