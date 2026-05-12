from datetime import datetime
from decimal import Decimal
import os
from unittest.mock import patch

import pytest
from django.utils import timezone

from trades.models import TradeRecord
from trades.tasks import run_hsbc_email_ingestion, run_ths_ingestion


class FakeEmailCrawler:
    last_config = None

    def __init__(self, config):
        self.config = config
        FakeEmailCrawler.last_config = config

    def fetch_hsbc_emails(self, since_date):
        return [
            {
                "subject": "全部執行: 買入 01712: 龍資源 的股/單位(交易編號: P880238)",
                "date": "2026-04-24T14:23:58+08:00",
                "body": (
                    "交易狀況：全部執行\n"
                    "指示類別：買入\n"
                    "股票名稱/ 股票編號：龍資源 (01712)\n"
                    "成交價：HKD 8.27\n"
                    "已成交數量(股/單位)：1,000\n"
                ),
            }
        ]

    def parse_trade_email(self, email):
        return {
            "stock_code": "01712",
            "stock_name": "龍資源",
            "market": TradeRecord.Market.HK_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": Decimal("8.27"),
            "quantity": 1000,
            "trade_time": timezone.make_aware(datetime(2026, 4, 24, 14, 23, 58), timezone.get_current_timezone()),
            "source": TradeRecord.Source.HSBC_EMAIL,
            "commission": Decimal("0"),
            "stamp_duty": Decimal("0"),
            "other_fees": Decimal("0"),
        }


@pytest.mark.django_db
def test_run_hsbc_email_ingestion_uses_configured_filters(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_PORT", "993")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_MAILBOX", "INBOX")
    monkeypatch.setenv(
        "IMAP_SENDER_FILTERS",
        "HSBC@notification.hsbc.com.hk,HSBC.estatement.and.eadvice@notification.hsbc.com.hk",
    )
    monkeypatch.setenv("IMAP_SUBJECT_INCLUDE_KEYWORDS", "全部執行,全部执行,買入,沽出,eAdvice,電子通知書")
    monkeypatch.setenv("IMAP_SUBJECT_EXCLUDE_KEYWORDS", "登入通知,Login Notification")

    with (
        patch("trades.tasks.is_cn_equity_trading_day", return_value=True),
        patch("trades.tasks.EmailCrawler", FakeEmailCrawler),
    ):
        created_count = run_hsbc_email_ingestion()

    assert created_count == 1
    assert FakeEmailCrawler.last_config["sender_filters"] == os.getenv("IMAP_SENDER_FILTERS")
    assert FakeEmailCrawler.last_config["subject_include_keywords"] == os.getenv("IMAP_SUBJECT_INCLUDE_KEYWORDS")
    assert FakeEmailCrawler.last_config["subject_exclude_keywords"] == os.getenv("IMAP_SUBJECT_EXCLUDE_KEYWORDS")
    assert TradeRecord.objects.filter(stock_code="01712", source=TradeRecord.Source.HSBC_EMAIL).count() == 1


class MixedEmailCrawler(FakeEmailCrawler):
    def fetch_hsbc_emails(self, since_date):
        return [{"subject": "bad-sell"}, {"subject": "good-buy"}]

    def parse_trade_email(self, email):
        if email["subject"] == "bad-sell":
            return {
                "stock_code": "00020",
                "stock_name": "Bad Sell",
                "market": TradeRecord.Market.HK_STOCK,
                "direction": TradeRecord.Direction.SELL,
                "price": Decimal("1.00"),
                "quantity": 1000,
                "trade_time": timezone.make_aware(datetime(2026, 4, 24, 10, 0, 0), timezone.get_current_timezone()),
                "source": TradeRecord.Source.HSBC_EMAIL,
                "commission": Decimal("0"),
                "stamp_duty": Decimal("0"),
                "other_fees": Decimal("0"),
            }
        return super().parse_trade_email(email)


@pytest.mark.django_db
def test_run_hsbc_email_ingestion_skips_invalid_trade_records(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_PORT", "993")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with (
        patch("trades.tasks.is_cn_equity_trading_day", return_value=True),
        patch("trades.tasks.EmailCrawler", MixedEmailCrawler),
    ):
        created_count = run_hsbc_email_ingestion()

    assert created_count == 1
    assert TradeRecord.objects.filter(stock_code="01712", source=TradeRecord.Source.HSBC_EMAIL).count() == 1


class HistoricalEmailCrawler(FakeEmailCrawler):
    def fetch_hsbc_emails(self, since_date):
        return [{"subject": "historical-buy"}]

    def parse_trade_email(self, email):
        return {
            "stock_code": "00189",
            "stock_name": "Historical",
            "market": TradeRecord.Market.HK_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": Decimal("12.15"),
            "quantity": 1000,
            "trade_time": timezone.make_aware(datetime(2026, 1, 27, 14, 41, 59), timezone.get_current_timezone()),
            "source": TradeRecord.Source.HSBC_EMAIL,
            "commission": Decimal("0"),
            "stamp_duty": Decimal("0"),
            "other_fees": Decimal("0"),
        }


@pytest.mark.django_db
def test_run_hsbc_email_ingestion_skips_trade_before_baseline(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_PORT", "993")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with (
        patch("trades.tasks.is_cn_equity_trading_day", return_value=True),
        patch("trades.tasks.EmailCrawler", HistoricalEmailCrawler),
    ):
        created_count = run_hsbc_email_ingestion()

    assert created_count == 0
    assert TradeRecord.objects.filter(stock_code="00189", source=TradeRecord.Source.HSBC_EMAIL).count() == 0


@pytest.mark.django_db
def test_run_ths_ingestion_skips_non_trading_day(monkeypatch):
    monkeypatch.setenv("THS_BRIDGE_PYTHON", "D:\\fake\\python.exe")

    with (
        patch("trades.tasks.is_cn_equity_trading_day", return_value=False),
        patch("trades.tasks.THSConnector") as connector_cls,
    ):
        created_count = run_ths_ingestion()

    assert created_count == 0
    connector_cls.assert_not_called()


@pytest.mark.django_db
def test_run_ths_ingestion_uses_macos_backend_without_windows_paths(monkeypatch):
    class FakeMacConnector:
        def __init__(self, config):
            self.config = config
            self.backend = "macos_ths_local"

        def test_connection(self):
            return True

        def fetch_trade_records(self, start_date, end_date):
            return [
                {
                    "stock_code": "603063",
                    "stock_name": "禾望电气",
                    "market": TradeRecord.Market.A_STOCK,
                    "direction": TradeRecord.Direction.BUY,
                    "price": Decimal("41.43"),
                    "quantity": 100,
                    "trade_time": timezone.make_aware(
                        datetime.combine(timezone.localdate(), datetime.min.time()),
                        timezone.get_current_timezone(),
                    ),
                    "source": TradeRecord.Source.THS,
                    "commission": Decimal("0"),
                    "stamp_duty": Decimal("0"),
                    "other_fees": Decimal("0"),
                }
            ]

    monkeypatch.setenv("THS_BACKEND", "macos_ths_local")
    monkeypatch.delenv("THS_EXE_PATH", raising=False)
    monkeypatch.delenv("THS_BRIDGE_PYTHON", raising=False)

    with (
        patch("trades.tasks.is_cn_equity_trading_day", return_value=True),
        patch("trades.tasks.THSConnector", FakeMacConnector),
    ):
        created_count = run_ths_ingestion()

    assert created_count == 1
    assert TradeRecord.objects.filter(stock_code="603063", source=TradeRecord.Source.THS).count() == 1


@pytest.mark.django_db
def test_run_hsbc_email_ingestion_skips_non_trading_day(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_PORT", "993")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with (
        patch("trades.tasks.is_cn_equity_trading_day", return_value=False),
        patch("trades.tasks.EmailCrawler") as crawler_cls,
    ):
        created_count = run_hsbc_email_ingestion()

    assert created_count == 0
    crawler_cls.assert_not_called()
