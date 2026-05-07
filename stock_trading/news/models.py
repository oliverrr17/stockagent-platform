from django.db import models


class NewsItem(models.Model):
    class Category(models.TextChoices):
        ANNOUNCEMENT = "ANNOUNCEMENT", "公告"
        SENTIMENT = "SENTIMENT", "舆情"
        RESEARCH = "RESEARCH", "研报"
        INDUSTRY = "INDUSTRY", "行业动态"

    stock_code = models.CharField(max_length=20, db_index=True)
    title = models.CharField(max_length=500)
    source = models.CharField(max_length=100)
    category = models.CharField(max_length=15, choices=Category.choices)
    summary = models.TextField(blank=True)
    url = models.URLField(max_length=1000)
    pushed = models.BooleanField(default=False)
    published_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["title", "source"]
        ordering = ["-published_at"]


class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        TELEGRAM = "TELEGRAM", "Telegram"
        WECHAT = "WECHAT", "微信"
        EMAIL = "EMAIL", "邮件"

    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "成功"
        FAILED = "FAILED", "失败"
        PENDING = "PENDING", "待发送"

    news_item = models.ForeignKey(NewsItem, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    retry_count = models.IntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)

