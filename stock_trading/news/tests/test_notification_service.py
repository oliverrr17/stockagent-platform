from django.core import mail
from django.test import override_settings
from django.utils import timezone

from news.models import NewsItem, NotificationLog
from news.services.notification_service import NotificationService
from trades.models import TradeRecord


def make_news(
    category=NewsItem.Category.ANNOUNCEMENT,
    title="公司公告",
    summary="summary",
    source="东方财富",
):
    return NewsItem(
        stock_code="603063",
        title=title,
        source=source,
        category=category,
        summary=summary,
        url="https://example.com/news",
        published_at=timezone.now(),
    )


def test_should_push_by_category_and_keywords():
    service = NotificationService()

    assert service.should_push(make_news(NewsItem.Category.ANNOUNCEMENT)) is True
    assert (
        service.should_push(
            make_news(
                NewsItem.Category.RESEARCH,
                title="\u6700\u65b0\u7814\u62a5\u4e0a\u8c03\u8bc4\u7ea7",
                source="\u65b0\u6d6a\u8d22\u7ecf",
            )
        )
        is False
    )
    assert (
        service.should_push(
            make_news(
                NewsItem.Category.INDUSTRY,
                title="\u884c\u4e1a\u666f\u6c14\u5ea6\u8ddf\u8e2a",
                source="\u65b0\u6d6a\u8d22\u7ecf",
            )
        )
        is False
    )
    assert (
        service.should_push(
            make_news(
                NewsItem.Category.SENTIMENT,
                title="\u91cd\u5927\u505c\u724c\u901a\u77e5",
                source="\u65b0\u6d6a\u8d22\u7ecf",
            )
        )
        is True
    )
    assert (
        service.should_push(
            make_news(
                NewsItem.Category.SENTIMENT,
                title="\u5e02\u573a\u70ed\u8bae",
                source="\u65b0\u6d6a\u8d22\u7ecf",
            )
        )
        is False
    )


def test_should_digest_for_p2_items():
    service = NotificationService()

    assert (
        service.should_digest(
            make_news(
                NewsItem.Category.RESEARCH,
                title="\u6700\u65b0\u7814\u62a5\u4e0a\u8c03\u8bc4\u7ea7",
                source="\u65b0\u6d6a\u8d22\u7ecf",
            )
        )
        is True
    )
    assert service.should_digest(make_news(NewsItem.Category.ANNOUNCEMENT, title="\u91cd\u5927\u505c\u724c\u516c\u544a")) is False
    assert (
        service.should_digest(
            make_news(
                NewsItem.Category.INDUSTRY,
                title="\u884c\u4e1a\u666f\u6c14\u5ea6\u8ddf\u8e2a",
                source="\u65b0\u6d6a\u8d22\u7ecf",
            )
        )
        is False
    )


def test_score_news_returns_priority_levels():
    service = NotificationService()

    p1 = service.score_news(make_news(NewsItem.Category.ANNOUNCEMENT, title="\u91cd\u5927\u505c\u724c\u516c\u544a"))
    p2 = service.score_news(
        make_news(
            NewsItem.Category.RESEARCH,
            title="\u6700\u65b0\u7814\u62a5\u4e0a\u8c03\u8bc4\u7ea7",
            source="\u65b0\u6d6a\u8d22\u7ecf",
        )
    )
    p3 = service.score_news(
        make_news(
            NewsItem.Category.INDUSTRY,
            title="\u884c\u4e1a\u666f\u6c14\u5ea6\u8ddf\u8e2a",
            source="\u65b0\u6d6a\u8d22\u7ecf",
        )
    )

    assert p1["priority_level"] == "P1"
    assert p2["priority_level"] == "P2"
    assert p3["priority_level"] == "P3"
    assert p1["priority_score"] > p2["priority_score"] > p3["priority_score"]


def test_is_trading_hours_returns_boolean():
    service = NotificationService()

    assert isinstance(service.is_trading_hours(TradeRecord.Market.A_STOCK), bool)
    assert isinstance(service.is_trading_hours(TradeRecord.Market.HK_STOCK), bool)


def test_push_without_sender_creates_pending_log(db):
    news = NewsItem.objects.create(
        stock_code="603063",
        title="\u516c\u53f8\u516c\u544a",
        source="\u4e1c\u65b9\u8d22\u5bcc",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now(),
    )
    service = NotificationService({"channel": NotificationLog.Channel.EMAIL, "recipients": []})

    result = service.push(news)

    assert result is False
    log = NotificationLog.objects.get(news_item=news)
    assert log.status == NotificationLog.Status.PENDING


def test_push_with_sender_marks_success(db):
    news = NewsItem.objects.create(
        stock_code="603063",
        title="\u91cd\u5927\u505c\u724c\u516c\u544a",
        source="\u4e1c\u65b9\u8d22\u5bcc",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now(),
    )
    service = NotificationService(
        {
            "channel": NotificationLog.Channel.EMAIL,
            "sender": lambda message, news_obj, channel: True,
        }
    )

    result = service.push(news)

    assert result is True
    news.refresh_from_db()
    assert news.pushed is True
    log = NotificationLog.objects.get(news_item=news)
    assert log.status == NotificationLog.Status.SUCCESS


def test_push_does_not_send_non_p1_even_with_sender(db):
    news = NewsItem.objects.create(
        stock_code="603063",
        title="\u6700\u65b0\u7814\u62a5\u4e0a\u8c03\u8bc4\u7ea7",
        source="\u65b0\u6d6a\u8d22\u7ecf",
        category=NewsItem.Category.RESEARCH,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now(),
    )
    called = {"count": 0}
    service = NotificationService(
        {
            "channel": NotificationLog.Channel.EMAIL,
            "sender": lambda message, news_obj, channel: called.__setitem__("count", called["count"] + 1) or True,
        }
    )

    result = service.push(news)

    assert result is False
    assert called["count"] == 0
    log = NotificationLog.objects.get(news_item=news)
    assert log.status == NotificationLog.Status.PENDING


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_push_with_email_channel_sends_email(db):
    news = NewsItem.objects.create(
        stock_code="603063",
        title="\u91cd\u5927\u505c\u724c\u516c\u544a",
        source="\u4e1c\u65b9\u8d22\u5bcc",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now(),
    )
    service = NotificationService(
        {
            "channel": NotificationLog.Channel.EMAIL,
            "recipients": ["notify@example.com"],
            "from_email": "stockagent@example.com",
        }
    )

    result = service.push(news)

    assert result is True
    assert len(mail.outbox) == 1
    assert news.title in mail.outbox[0].subject
    log = NotificationLog.objects.get(news_item=news)
    assert log.status == NotificationLog.Status.SUCCESS


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_push_digest_sends_summary_for_p2_items(db):
    p2_news = NewsItem.objects.create(
        stock_code="603063",
        title="\u6700\u65b0\u7814\u62a5\u4e0a\u8c03\u8bc4\u7ea7",
        source="\u65b0\u6d6a\u8d22\u7ecf",
        category=NewsItem.Category.RESEARCH,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now(),
    )
    p3_news = NewsItem.objects.create(
        stock_code="600873",
        title="\u884c\u4e1a\u666f\u6c14\u5ea6\u8ddf\u8e2a",
        source="\u65b0\u6d6a\u8d22\u7ecf",
        category=NewsItem.Category.INDUSTRY,
        summary="summary",
        url="https://example.com/news2",
        published_at=timezone.now(),
    )
    service = NotificationService(
        {
            "channel": NotificationLog.Channel.EMAIL,
            "recipients": ["notify@example.com"],
            "from_email": "stockagent@example.com",
        }
    )

    result = service.push_digest([p2_news, p3_news])

    assert result is True
    assert len(mail.outbox) == 1
    assert "News Summary" in mail.outbox[0].subject
    p2_news.refresh_from_db()
    p3_news.refresh_from_db()
    assert p2_news.pushed is True
    assert p3_news.pushed is False
    assert NotificationLog.objects.filter(news_item=p2_news, status=NotificationLog.Status.SUCCESS).exists()
    assert not NotificationLog.objects.filter(news_item=p3_news).exists()
