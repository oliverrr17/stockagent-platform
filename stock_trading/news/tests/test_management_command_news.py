from unittest.mock import patch

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_news_crawl_management_command_emits_json_summary(capsys):
    with patch("news.management.commands.crawl_portfolio_news_now.crawl_portfolio_news", return_value=3):
        call_command("crawl_portfolio_news_now", json=True)

    captured = capsys.readouterr()
    assert '"created_count": 3' in captured.out


@pytest.mark.django_db
def test_news_crawl_management_command_prints_success_summary(capsys):
    with patch("news.management.commands.crawl_portfolio_news_now.crawl_portfolio_news", return_value=2):
        call_command("crawl_portfolio_news_now")

    captured = capsys.readouterr()
    assert "created 2 new NewsItem row" in captured.out
