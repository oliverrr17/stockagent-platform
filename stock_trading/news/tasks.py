from __future__ import annotations

import logging
import os

from celery import shared_task

from news.models import NewsItem
from news.services.news_crawler import NewsCrawler
from news.services.notification_service import NotificationService
from portfolio.models import Position
from trades.models import TradeRecord


logger = logging.getLogger(__name__)


@shared_task
def crawl_portfolio_news() -> int:
    crawler = NewsCrawler()
    created_count = 0
    auto_push = os.getenv("NEWS_NOTIFY_AUTO_PUSH", "False").lower() == "true"

    positions = Position.objects.filter(status=Position.Status.ACTIVE, quantity__gt=0)
    for position in positions:
        if position.market == TradeRecord.Market.A_STOCK:
            items = crawler.crawl_a_stock_news(position.stock_code)
        elif position.market == TradeRecord.Market.HK_STOCK:
            items = crawler.crawl_hk_stock_news(position.stock_code)
        else:
            items = []

        for item in items:
            news_item, created = NewsItem.objects.get_or_create(
                title=item["title"],
                source=item["source"],
                defaults={
                    "stock_code": item["stock_code"],
                    "category": item["category"],
                    "summary": item["summary"],
                    "url": item["url"],
                    "published_at": item["published_at"],
                },
            )
            created_count += int(created)
            if created and auto_push:
                push_notification(news_item.id)

    return created_count


@shared_task
def push_notification(news_item_id: int) -> bool:
    try:
        news = NewsItem.objects.get(pk=news_item_id)
    except NewsItem.DoesNotExist:
        logger.warning("News item %s does not exist; skip notification.", news_item_id)
        return False

    service = NotificationService()
    if not service.should_push(news):
        return False
    return service.push(news)


@shared_task
def push_news_digest() -> bool:
    service = NotificationService()
    items = list(NewsItem.objects.filter(pushed=False).order_by("-published_at"))
    return service.push_digest(items)
