import os

from celery import Celery
from celery.schedules import crontab


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_trading.config.settings")

app = Celery("stock_trading")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

ths_hour = int(os.getenv("THS_FETCH_HOUR", "16"))
ths_minute = int(os.getenv("THS_FETCH_MINUTE", "10"))
hsbc_hour = int(os.getenv("HSBC_FETCH_HOUR", "18"))
hsbc_minute = int(os.getenv("HSBC_FETCH_MINUTE", "30"))
futu_hour = int(os.getenv("FUTU_FETCH_HOUR", "18"))
futu_minute = int(os.getenv("FUTU_FETCH_MINUTE", "35"))
news_hours = os.getenv("NEWS_FETCH_HOURS", "8,9,10,11,12,13,14,15,16,17,18,19,20,21,22")
news_minute = int(os.getenv("NEWS_FETCH_MINUTE", "0"))
news_digest_hour = int(os.getenv("NEWS_DIGEST_HOUR", "18"))
news_digest_minute = int(os.getenv("NEWS_DIGEST_MINUTE", "35"))
market_snapshot_hour = int(os.getenv("MARKET_SNAPSHOT_HOUR", "18"))
market_snapshot_minute = int(os.getenv("MARKET_SNAPSHOT_MINUTE", "45"))

app.conf.beat_schedule = {
    "fetch-ths-trades-daily": {
        "task": "trades.tasks.fetch_ths_trades",
        "schedule": crontab(hour=ths_hour, minute=ths_minute, day_of_week="mon-fri"),
    },
    "fetch-hsbc-email-trades-daily": {
        "task": "trades.tasks.fetch_hsbc_email_trades",
        "schedule": crontab(hour=hsbc_hour, minute=hsbc_minute, day_of_week="mon-fri"),
    },
    "fetch-futu-trades-daily": {
        "task": "trades.tasks.fetch_futu_trades",
        "schedule": crontab(hour=futu_hour, minute=futu_minute, day_of_week="mon-fri"),
    },
    "crawl-portfolio-news-daily": {
        "task": "news.tasks.crawl_portfolio_news",
        "schedule": crontab(hour=news_hours, minute=news_minute),
    },
    "push-news-digest-daily": {
        "task": "news.tasks.push_news_digest",
        "schedule": crontab(hour=news_digest_hour, minute=news_digest_minute),
    },
    "refresh-market-price-snapshots-daily": {
        "task": "portfolio.tasks.refresh_market_price_snapshots",
        "schedule": crontab(hour=market_snapshot_hour, minute=market_snapshot_minute, day_of_week="mon-fri"),
    },
}
