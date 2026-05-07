from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from news.models import NewsItem, NotificationLog
from news.services.notification_service import NotificationService
from news.tasks import crawl_portfolio_news, push_news_digest, push_notification
from portfolio.models import Position
from trades.models import TradeRecord


@pytest.mark.django_db
def test_crawl_portfolio_news_creates_items():
    Position.objects.create(
        stock_code="603063",
        stock_name="\u79be\u671b\u7535\u6c14",
        market=TradeRecord.Market.A_STOCK,
        quantity=100,
        cost_price="41.4300",
        weighted_avg_cost="41.4300",
        total_invested="4143.0000",
        realized_pnl="0",
        status=Position.Status.ACTIVE,
    )

    fake_items = [
        {
            "stock_code": "603063",
            "title": "\u516c\u53f8\u516c\u544a",
            "source": "\u4e1c\u65b9\u8d22\u5bcc",
            "category": NewsItem.Category.ANNOUNCEMENT,
            "summary": "summary",
            "url": "https://example.com/news",
            "published_at": timezone.now(),
        }
    ]

    with patch("news.tasks.NewsCrawler.crawl_a_stock_news", return_value=fake_items):
        created_count = crawl_portfolio_news()

    assert created_count == 1
    assert NewsItem.objects.count() == 1


@pytest.mark.django_db
def test_crawl_portfolio_news_ignores_cleared_positions():
    Position.objects.create(
        stock_code="603063",
        stock_name="\u79be\u671b\u7535\u6c14",
        market=TradeRecord.Market.A_STOCK,
        quantity=0,
        cost_price="41.4300",
        weighted_avg_cost="41.4300",
        total_invested="0.0000",
        realized_pnl="100.0000",
        status=Position.Status.CLEARED,
    )

    with patch("news.tasks.NewsCrawler.crawl_a_stock_news", return_value=[]) as crawl_mock:
        created_count = crawl_portfolio_news()

    assert created_count == 0
    crawl_mock.assert_not_called()


@pytest.mark.django_db
def test_push_notification_creates_pending_log_without_sender():
    news = NewsItem.objects.create(
        stock_code="603063",
        title="\u516c\u53f8\u516c\u544a",
        source="\u4e1c\u65b9\u8d22\u5bcc",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now() - timedelta(minutes=5),
    )

    with patch(
        "news.tasks.NotificationService",
        return_value=NotificationService({"channel": NotificationLog.Channel.EMAIL, "recipients": []}),
    ):
        result = push_notification(news.id)

    assert result is False
    assert NotificationLog.objects.filter(news_item=news).count() == 1


@pytest.mark.django_db
def test_push_notification_suppresses_non_p1_news():
    news = NewsItem.objects.create(
        stock_code="603063",
        title="\u6700\u65b0\u7814\u62a5\u4e0a\u8c03\u8bc4\u7ea7",
        source="\u65b0\u6d6a\u8d22\u7ecf",
        category=NewsItem.Category.RESEARCH,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now() - timedelta(minutes=5),
    )

    result = push_notification(news.id)

    assert result is False
    assert NotificationLog.objects.filter(news_item=news).count() == 0


@pytest.mark.django_db
def test_crawl_portfolio_news_can_trigger_push_for_new_items():
    Position.objects.create(
        stock_code="603063",
        stock_name="\u79be\u671b\u7535\u6c14",
        market=TradeRecord.Market.A_STOCK,
        quantity=100,
        cost_price="41.4300",
        weighted_avg_cost="41.4300",
        total_invested="4143.0000",
        realized_pnl="0",
        status=Position.Status.ACTIVE,
    )
    fake_items = [
        {
            "stock_code": "603063",
            "title": "\u91cd\u5927\u505c\u724c\u516c\u544a",
            "source": "\u4e1c\u65b9\u8d22\u5bcc",
            "category": NewsItem.Category.ANNOUNCEMENT,
            "summary": "summary",
            "url": "https://example.com/news",
            "published_at": timezone.now(),
        }
    ]

    with (
        patch("news.tasks.NewsCrawler.crawl_a_stock_news", return_value=fake_items),
        patch("news.tasks.push_notification", return_value=True) as push_mock,
        patch.dict("os.environ", {"NEWS_NOTIFY_AUTO_PUSH": "True"}),
    ):
        created_count = crawl_portfolio_news()

    assert created_count == 1
    push_mock.assert_called_once()


@pytest.mark.django_db
def test_push_news_digest_processes_pending_p2_items():
    p2_news = NewsItem.objects.create(
        stock_code="603063",
        title="\u6700\u65b0\u7814\u62a5\u4e0a\u8c03\u8bc4\u7ea7",
        source="\u65b0\u6d6a\u8d22\u7ecf",
        category=NewsItem.Category.RESEARCH,
        summary="summary",
        url="https://example.com/news",
        published_at=timezone.now(),
    )

    with patch(
        "news.tasks.NotificationService",
        return_value=NotificationService(
            {
                "channel": NotificationLog.Channel.EMAIL,
                "sender": lambda message, items, channel: True,
            }
        ),
    ):
        result = push_news_digest()

    assert result is True
    p2_news.refresh_from_db()
    assert p2_news.pushed is True
