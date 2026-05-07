from rest_framework import serializers

from .models import NewsItem, NotificationLog
from .services.notification_service import NotificationService


class NewsItemSerializer(serializers.ModelSerializer):
    priority_score = serializers.SerializerMethodField()
    priority_level = serializers.SerializerMethodField()
    matched_rules = serializers.SerializerMethodField()
    latest_notification_status = serializers.SerializerMethodField()
    latest_notification_channel = serializers.SerializerMethodField()
    notification_count = serializers.SerializerMethodField()

    class Meta:
        model = NewsItem
        fields = [
            "id",
            "stock_code",
            "title",
            "source",
            "category",
            "summary",
            "url",
            "pushed",
            "published_at",
            "created_at",
            "priority_score",
            "priority_level",
            "matched_rules",
            "latest_notification_status",
            "latest_notification_channel",
            "notification_count",
        ]

    def get_priority_score(self, obj):
        return NotificationService().score_news(obj)["priority_score"]

    def get_priority_level(self, obj):
        return NotificationService().score_news(obj)["priority_level"]

    def get_matched_rules(self, obj):
        return NotificationService().score_news(obj)["matched_rules"]

    def get_latest_notification_status(self, obj):
        latest = obj.notifications.order_by("-id").first()
        return latest.status if latest else ""

    def get_latest_notification_channel(self, obj):
        latest = obj.notifications.order_by("-id").first()
        return latest.channel if latest else ""

    def get_notification_count(self, obj):
        return obj.notifications.count()


class NotificationLogSerializer(serializers.ModelSerializer):
    stock_code = serializers.CharField(source="news_item.stock_code", read_only=True)
    news_title = serializers.CharField(source="news_item.title", read_only=True)
    news_source = serializers.CharField(source="news_item.source", read_only=True)
    news_category = serializers.CharField(source="news_item.category", read_only=True)
    news_published_at = serializers.DateTimeField(source="news_item.published_at", read_only=True)
    priority_score = serializers.SerializerMethodField()
    priority_level = serializers.SerializerMethodField()
    matched_rules = serializers.SerializerMethodField()

    class Meta:
        model = NotificationLog
        fields = [
            "id",
            "news_item",
            "stock_code",
            "news_title",
            "news_source",
            "news_category",
            "news_published_at",
            "channel",
            "status",
            "retry_count",
            "sent_at",
            "priority_score",
            "priority_level",
            "matched_rules",
        ]

    def get_priority_score(self, obj):
        return NotificationService().score_news(obj.news_item)["priority_score"]

    def get_priority_level(self, obj):
        return NotificationService().score_news(obj.news_item)["priority_level"]

    def get_matched_rules(self, obj):
        return NotificationService().score_news(obj.news_item)["matched_rules"]
