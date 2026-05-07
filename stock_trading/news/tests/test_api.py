from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from news.models import NewsItem, NotificationLog


@pytest.fixture
def api_client(db):
    user = get_user_model().objects.create_user(username="news-api", password="secret")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_news_list_can_filter_by_stock_code(api_client):
    now = timezone.now()
    NewsItem.objects.create(
        stock_code="603063",
        title="禾望电气公告",
        source="东方财富",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/1",
        published_at=now,
    )
    NewsItem.objects.create(
        stock_code="02610",
        title="南山铝业国际公告",
        source="披露易",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/2",
        published_at=now - timedelta(hours=1),
    )

    response = api_client.get("/api/news/?stock_code=603063")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["stock_code"] == "603063"


@pytest.mark.django_db
def test_news_list_can_filter_by_category(api_client):
    now = timezone.now()
    NewsItem.objects.create(
        stock_code="603063",
        title="禾望电气公告",
        source="东方财富",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/1",
        published_at=now,
    )
    NewsItem.objects.create(
        stock_code="603063",
        title="禾望电气研报",
        source="新浪财经",
        category=NewsItem.Category.RESEARCH,
        summary="summary",
        url="https://example.com/2",
        published_at=now,
    )

    response = api_client.get(f"/api/news/?category={NewsItem.Category.RESEARCH}")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["category"] == NewsItem.Category.RESEARCH


@pytest.mark.django_db
def test_news_list_can_filter_by_source_and_query(api_client):
    now = timezone.now()
    NewsItem.objects.create(
        stock_code="603063",
        title="禾望电气公告",
        source="东方财富",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/1",
        published_at=now,
    )
    NewsItem.objects.create(
        stock_code="603063",
        title="禾望电气研报",
        source="新浪财经",
        category=NewsItem.Category.RESEARCH,
        summary="评级上调",
        url="https://example.com/2",
        published_at=now,
    )

    response = api_client.get("/api/news/?source=新浪财经&query=评级")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["source"] == "新浪财经"


@pytest.mark.django_db
def test_notification_log_list_returns_nested_news_context(api_client):
    news = NewsItem.objects.create(
        stock_code="603063",
        title="禾望电气公告",
        source="东方财富",
        category=NewsItem.Category.ANNOUNCEMENT,
        summary="summary",
        url="https://example.com/1",
        published_at=timezone.now(),
    )
    NotificationLog.objects.create(
        news_item=news,
        channel=NotificationLog.Channel.EMAIL,
        status=NotificationLog.Status.SUCCESS,
    )

    response = api_client.get("/api/news/notifications/?stock_code=603063")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["stock_code"] == "603063"
    assert payload[0]["news_title"] == "禾望电气公告"
