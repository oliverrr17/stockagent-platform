from datetime import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from trades.models import TradeRecord
from trades.services.email_crawler import EmailCrawler


@pytest.fixture
def crawler():
    return EmailCrawler(config={})


def test_parse_trade_email_with_english_template(crawler):
    email_payload = {
        "subject": "Fully Executed: BUY00700: Tencent Holdings的股/單位(交易編號: P520268)",
        "date": "2026-04-17T10:30:00+08:00",
        "body": """\
Market: HK_STOCK
Stock Code: 00700
Stock Name: Tencent Holdings
Side: BUY
Price: HKD 320.50
Quantity: 100
Commission: HKD 10.50
Stamp Duty: HKD 3.20
Other Fees: HKD 1.80
""",
    }

    parsed = crawler.parse_trade_email(email_payload)

    assert parsed["stock_code"] == "00700"
    assert parsed["stock_name"] == "Tencent Holdings"
    assert parsed["direction"] == TradeRecord.Direction.BUY
    assert parsed["market"] == TradeRecord.Market.HK_STOCK
    assert parsed["price"] == Decimal("320.50")
    assert parsed["quantity"] == 100
    assert parsed["commission"] == Decimal("10.50")


def test_parse_trade_email_with_chinese_template(crawler):
    email_body = (
        "\u4ea4\u6613\u72c0\u6cc1\uff1a\u5168\u90e8\u57f7\u884c\n"
        "\u6307\u793a\u985e\u5225\uff1a\u6cbd\u51fa\n"
        "\u80a1\u7968\u540d\u7a31/ \u80a1\u7968\u7de8\u865f\uff1a\u5c0f\u7c73\u96c6\u5718 (01810)\n"
        "\u6210\u4ea4\u50f9\uff1aHKD 18.24\n"
        "\u5df2\u6210\u4ea4\u6578\u91cf(\u80a1/\u55ae\u4f4d)\uff1a2,000\n"
        "\u4f63\u91d1\uff1aHKD 8.00\n"
        "\u5370\u82b1\u7a05\uff1aHKD 1.00\n"
        "\u5176\u4ed6\u8cbb\u7528\uff1aHKD 0.50\n"
    )

    parsed = crawler.parse_trade_email(
        {
            "subject": "\u5168\u90e8\u57f7\u884c: \u6cbd\u51fa01810: \u5c0f\u7c73\u96c6\u5718\u7684\u80a1/\u55ae\u4f4d(\u4ea4\u6613\u7de8\u865f: S258403)",
            "date": "2026-04-17T09:35:00+08:00",
            "body": email_body,
        }
    )

    assert parsed["stock_code"] == "01810"
    assert parsed["stock_name"] == "\u5c0f\u7c73\u96c6\u5718"
    assert parsed["direction"] == TradeRecord.Direction.SELL
    assert parsed["market"] == TradeRecord.Market.HK_STOCK
    assert parsed["quantity"] == 2000
    assert parsed["price"] == Decimal("18.24")


def test_parse_trade_email_with_full_width_colons_and_compact_subject(crawler):
    parsed = crawler.parse_trade_email(
        {
            "subject": "全部執行：沽出07709:XL二南方海力士的股/單位(交易編號：S258403)",
            "date": "2026-04-17T09:35:00+08:00",
            "body": (
                "交易狀況：全部執行\n"
                "指示類別：沽出\n"
                "股票名稱/ 股票編號：XL二南方海力士 (07709)\n"
                "成交價：HKD21.70\n"
                "已成交數量(股/單位)：400\n"
            ),
        }
    )

    assert parsed["stock_code"] == "07709"
    assert parsed["stock_name"] == "XL二南方海力士"
    assert parsed["direction"] == TradeRecord.Direction.SELL
    assert parsed["price"] == Decimal("21.70")
    assert parsed["quantity"] == 400


def test_format_and_parse_trade_record_round_trip(crawler):
    trade_time = timezone.make_aware(datetime(2026, 4, 17, 14, 20, 0), timezone.get_current_timezone())
    record = {
        "market": TradeRecord.Market.HK_STOCK,
        "stock_code": "00941",
        "stock_name": "China Mobile",
        "direction": TradeRecord.Direction.BUY,
        "price": Decimal("75.2500"),
        "quantity": 300,
        "trade_time": trade_time,
        "commission": Decimal("12.0000"),
        "stamp_duty": Decimal("2.5000"),
        "other_fees": Decimal("1.0000"),
    }

    formatted = crawler.format_trade_record(record)
    reparsed = crawler.parse_trade_email(formatted)

    assert reparsed["market"] == record["market"]
    assert reparsed["stock_code"] == record["stock_code"]
    assert reparsed["stock_name"] == record["stock_name"]
    assert reparsed["direction"] == record["direction"]
    assert reparsed["price"] == record["price"]
    assert reparsed["quantity"] == record["quantity"]
    assert reparsed["trade_time"] == record["trade_time"]
    assert reparsed["commission"] == record["commission"]
    assert reparsed["stamp_duty"] == record["stamp_duty"]
    assert reparsed["other_fees"] == record["other_fees"]


def test_parse_trade_email_rejects_cancelled_trade(crawler):
    cancelled_email = {
        "subject": "\u5168\u90e8\u53d6\u6d88: \u8cb7\u516500100: MINIMAX-WP\u7684\u80a1/\u55ae\u4f4d(\u4ea4\u6613\u7de8\u865f: P504252)",
        "date": "2026-04-17T09:35:00+08:00",
        "body": (
            "\u4ea4\u6613\u72c0\u6cc1: \u5168\u90e8\u53d6\u6d88\n"
            "\u6307\u793a\u985e\u5225: \u8cb7\u5165\n"
            "\u80a1\u7968\u540d\u7a31/ \u80a1\u7968\u7de8\u865f: MINIMAX-WP (00100)"
        ),
    }

    with pytest.raises(ValueError, match="Cancelled"):
        crawler.parse_trade_email(cancelled_email)
