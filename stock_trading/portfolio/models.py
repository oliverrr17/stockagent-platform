from django.db import models

from trades.models import TradeRecord


class Position(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "持仓中"
        CLEARED = "CLEARED", "已清仓"

    stock_code = models.CharField(max_length=20, db_index=True)
    stock_name = models.CharField(max_length=100)
    market = models.CharField(max_length=10, choices=TradeRecord.Market.choices)
    quantity = models.IntegerField(default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=4)
    weighted_avg_cost = models.DecimalField(max_digits=12, decimal_places=4)
    total_invested = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    realized_pnl = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class PositionEntry(models.Model):
    stock_code = models.CharField(max_length=20)
    stock_name = models.CharField(max_length=100)
    market = models.CharField(max_length=10, choices=TradeRecord.Market.choices)
    quantity = models.IntegerField()
    cost_price = models.DecimalField(max_digits=12, decimal_places=4)
    entry_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class CashAccount(models.Model):
    class Currency(models.TextChoices):
        CNY = "CNY", "人民币"
        HKD = "HKD", "港币"

    currency = models.CharField(max_length=3, choices=Currency.choices, unique=True)
    label = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["currency"]


class CashFlow(models.Model):
    class Direction(models.TextChoices):
        DEPOSIT = "DEPOSIT", "入金"
        WITHDRAWAL = "WITHDRAWAL", "出金"

    cash_account = models.ForeignKey(CashAccount, on_delete=models.CASCADE, related_name="flows")
    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    occurred_at = models.DateTimeField(db_index=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]


class FXRate(models.Model):
    base_currency = models.CharField(max_length=3)
    quote_currency = models.CharField(max_length=3)
    rate_date = models.DateField(db_index=True)
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    source = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["base_currency", "quote_currency", "rate_date"]
        ordering = ["-rate_date"]


class PortfolioPerformanceSnapshot(models.Model):
    class AuditStatus(models.TextChoices):
        FINAL = "FINAL", "Final"
        PROVISIONAL = "PROVISIONAL", "Provisional"

    snapshot_date = models.DateField(unique=True, db_index=True)
    total_assets_cny = models.DecimalField(max_digits=18, decimal_places=4)
    total_return_cny = models.DecimalField(max_digits=18, decimal_places=4)
    daily_return_pct = models.DecimalField(max_digits=12, decimal_places=4)
    monthly_return_pct = models.DecimalField(max_digits=12, decimal_places=4)
    yearly_return_pct = models.DecimalField(max_digits=12, decimal_places=4)
    cumulative_return_pct = models.DecimalField(max_digits=12, decimal_places=4)
    audit_status = models.CharField(max_length=12, choices=AuditStatus.choices, default=AuditStatus.PROVISIONAL)
    external_flow_cny = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    computed_daily_pnl_cny = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["snapshot_date"]


class PositionDailyContributionSnapshot(models.Model):
    class AuditStatus(models.TextChoices):
        FINAL = "FINAL", "Final"
        PROVISIONAL = "PROVISIONAL", "Provisional"

    snapshot_date = models.DateField(db_index=True)
    stock_code = models.CharField(max_length=20, db_index=True)
    stock_name = models.CharField(max_length=100, blank=True)
    market = models.CharField(max_length=10, choices=TradeRecord.Market.choices)
    start_quantity = models.IntegerField(default=0)
    end_quantity = models.IntegerField(default=0)
    previous_close = models.DecimalField(max_digits=12, decimal_places=4)
    latest_price = models.DecimalField(max_digits=12, decimal_places=4)
    trade_cash_delta = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    daily_pnl_native = models.DecimalField(max_digits=18, decimal_places=4)
    daily_pnl_cny = models.DecimalField(max_digits=18, decimal_places=4)
    fx_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1)
    price_source = models.CharField(max_length=50)
    source_trade_date = models.DateField(null=True, blank=True)
    degraded = models.BooleanField(default=False)
    degraded_reason = models.CharField(max_length=200, blank=True)
    audit_status = models.CharField(max_length=12, choices=AuditStatus.choices, default=AuditStatus.PROVISIONAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["snapshot_date", "market", "stock_code"]
        unique_together = ["snapshot_date", "stock_code", "market"]


class SecurityPriceSnapshot(models.Model):
    stock_code = models.CharField(max_length=20, db_index=True)
    stock_name = models.CharField(max_length=100, blank=True)
    market = models.CharField(max_length=10, choices=TradeRecord.Market.choices)
    trade_date = models.DateField(db_index=True)
    close_price = models.DecimalField(max_digits=12, decimal_places=4)
    previous_close = models.DecimalField(max_digits=12, decimal_places=4)
    open_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    high_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    low_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    volume = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    amount = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    source = models.CharField(max_length=50)
    degraded = models.BooleanField(default=False)
    degraded_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["stock_code", "market", "trade_date"]
        ordering = ["trade_date", "stock_code"]
