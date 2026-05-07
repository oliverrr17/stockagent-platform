from django.db import models


class TradeRecord(models.Model):
    class Market(models.TextChoices):
        A_STOCK = "A_STOCK", "A股"
        HK_STOCK = "HK_STOCK", "港股"

    class Direction(models.TextChoices):
        BUY = "BUY", "买入"
        SELL = "SELL", "卖出"

    class Source(models.TextChoices):
        THS = "THS", "同花顺"
        HSBC_EMAIL = "HSBC_EMAIL", "汇丰邮件"
        MANUAL = "MANUAL", "手动录入"

    stock_code = models.CharField(max_length=20, db_index=True)
    stock_name = models.CharField(max_length=100)
    market = models.CharField(max_length=10, choices=Market.choices)
    direction = models.CharField(max_length=4, choices=Direction.choices)
    price = models.DecimalField(max_digits=12, decimal_places=4)
    quantity = models.IntegerField()
    commission = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    stamp_duty = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    other_fees = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    trade_time = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=12, choices=Source.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["stock_code", "trade_time", "direction", "quantity", "price"]
        ordering = ["-trade_time"]


class TradeIntentSnapshot(models.Model):
    trade_record = models.OneToOneField(TradeRecord, on_delete=models.CASCADE, related_name="intent_snapshot")
    setup_tags = models.JSONField(default=list, blank=True)
    market_context_tags = models.JSONField(default=list, blank=True)
    security_quality_tags = models.JSONField(default=list, blank=True)
    execution_emotion_tags = models.JSONField(default=list, blank=True)
    overall_notes = models.CharField(max_length=400, blank=True)
    planned_holding_period = models.CharField(max_length=20, blank=True)
    planned_stop_loss_type = models.CharField(max_length=30, blank=True)
    planned_stop_loss_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    planned_take_profit_type = models.CharField(max_length=30, blank=True)
    planned_take_profit_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
