import importlib
import os
import sys


def test_celery_news_fetch_defaults_cover_every_hour_from_8_to_22(monkeypatch):
    monkeypatch.delenv("NEWS_FETCH_HOURS", raising=False)
    monkeypatch.delenv("NEWS_FETCH_MINUTE", raising=False)

    sys.modules.pop("stock_trading.config.celery", None)
    sys.modules.pop("stock_trading.config", None)

    module = importlib.import_module("stock_trading.config.celery")

    assert module.news_hours == "8,9,10,11,12,13,14,15,16,17,18,19,20,21,22"
    assert module.news_minute == 0
