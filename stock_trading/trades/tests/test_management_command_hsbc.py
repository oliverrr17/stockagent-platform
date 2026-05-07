from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from trades.models import TradeRecord


class FakeEmailCrawler:
    def __init__(self, config):
        self.config = config
        self.closed = False

    def test_connection(self):
        return True

    def fetch_hsbc_emails(self, since_date):
        return [
            {"subject": "executed-one"},
            {"subject": "cancelled-one"},
        ]

    def parse_trade_email(self, email):
        if email["subject"] == "cancelled-one":
            raise ValueError("Cancelled trade email should not be recorded.")
        return {
            "stock_code": "02610",
            "stock_name": "南山铝业国际",
            "market": TradeRecord.Market.HK_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": Decimal("58.50"),
            "quantity": 100,
            "trade_time": timezone.now(),
            "source": TradeRecord.Source.HSBC_EMAIL,
            "commission": Decimal("0"),
            "stamp_duty": Decimal("0"),
            "other_fees": Decimal("0"),
        }

    def close(self):
        self.closed = True


class HistoricalEmailCrawler(FakeEmailCrawler):
    def fetch_hsbc_emails(self, since_date):
        return [{"subject": "historical-one"}]

    def parse_trade_email(self, email):
        return {
            "stock_code": "00189",
            "stock_name": "鍘嗗彶浜ゆ槗",
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
def test_hsbc_management_command_can_test_connection(capsys):
    with patch("trades.management.commands.fetch_hsbc_email_trades_now.EmailCrawler", FakeEmailCrawler):
        call_command(
            "fetch_hsbc_email_trades_now",
            test_connection=True,
            host="imap.example.com",
            username="user@example.com",
            password="secret",
        )

    captured = capsys.readouterr()
    assert "IMAP connection succeeded" in captured.out


@pytest.mark.django_db
def test_hsbc_management_command_dry_run_outputs_json(tmp_path, capsys):
    output_file = tmp_path / "hsbc_payload.json"
    with patch("trades.management.commands.fetch_hsbc_email_trades_now.EmailCrawler", FakeEmailCrawler):
        call_command(
            "fetch_hsbc_email_trades_now",
            dry_run=True,
            json=True,
            output_file=str(output_file),
            host="imap.example.com",
            username="user@example.com",
            password="secret",
        )

    captured = capsys.readouterr()
    assert '"stock_code": "02610"' in captured.out
    assert "dry-run only" in captured.out
    payload = json.loads(Path(output_file).read_text(encoding="utf-8"))
    assert payload[0]["stock_name"] == "南山铝业国际"
    assert TradeRecord.objects.count() == 0


@pytest.mark.django_db
def test_hsbc_management_command_persists_parsed_trades(capsys):
    with patch("trades.management.commands.fetch_hsbc_email_trades_now.EmailCrawler", FakeEmailCrawler):
        call_command(
            "fetch_hsbc_email_trades_now",
            host="imap.example.com",
            username="user@example.com",
            password="secret",
        )

    captured = capsys.readouterr()
    assert "created 1 new TradeRecord row" in captured.out
    assert TradeRecord.objects.filter(stock_code="02610").count() == 1


@pytest.mark.django_db
def test_hsbc_management_command_skips_historical_trade_before_baseline(capsys):
    with patch("trades.management.commands.fetch_hsbc_email_trades_now.EmailCrawler", HistoricalEmailCrawler):
        call_command(
            "fetch_hsbc_email_trades_now",
            host="imap.example.com",
            username="user@example.com",
            password="secret",
        )

    captured = capsys.readouterr()
    assert "created 0 new TradeRecord row" in captured.out
    assert TradeRecord.objects.filter(stock_code="00189").count() == 0
