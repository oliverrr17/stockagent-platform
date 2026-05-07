from __future__ import annotations

from datetime import timedelta
import logging
import os

from celery import shared_task
from django.utils import timezone

from config.trading_calendar import is_cn_equity_trading_day
from trades.ingestion_policy import is_trade_before_ingestion_start
from trades.services.email_crawler import EmailCrawler
from trades.services.ths_connector import THSConnector
from trades.services.trade_recorder import TradeRecorder


logger = logging.getLogger(__name__)


def run_ths_ingestion() -> int:
    today = timezone.localdate()
    if not is_cn_equity_trading_day(today):
        logger.info("Skipping THS trade fetch on non-trading day %s.", today)
        return 0

    exe_path = os.getenv("THS_EXE_PATH", "").strip()
    bridge_python = os.getenv("THS_BRIDGE_PYTHON", "").strip()
    if not exe_path and not bridge_python:
        logger.warning("THS_EXE_PATH or THS_BRIDGE_PYTHON must be configured; skipping THS trade fetch.")
        return 0

    connector = THSConnector(
        {
            "exe_path": exe_path or None,
            "client_type": os.getenv("THS_CLIENT_TYPE", "ths"),
            "bridge_python": bridge_python or None,
            "window_title_keyword": os.getenv("THS_WINDOW_TITLE_KEYWORD", "股票交易系统"),
        }
    )
    records = connector.fetch_trade_records(today, today)
    recorder = TradeRecorder()
    created_count = 0
    for record in records:
        _, created = recorder.record_trade(record)
        created_count += int(created)
    return created_count


@shared_task(autoretry_for=(Exception,), max_retries=3, retry_backoff=60)
def fetch_ths_trades() -> int:
    return run_ths_ingestion()


def run_hsbc_email_ingestion() -> int:
    today = timezone.localdate()
    if not is_cn_equity_trading_day(today):
        logger.info("Skipping HSBC email fetch on non-trading day %s.", today)
        return 0

    crawler = EmailCrawler(
        {
            "host": os.getenv("IMAP_HOST"),
            "port": int(os.getenv("IMAP_PORT", "993")),
            "username": os.getenv("IMAP_USERNAME"),
            "password": os.getenv("IMAP_PASSWORD"),
            "mailbox": os.getenv("IMAP_MAILBOX", "INBOX"),
            "sender_keyword": os.getenv("IMAP_SENDER_KEYWORD", "hsbc"),
            "sender_filters": os.getenv("IMAP_SENDER_FILTERS", ""),
            "subject_include_keywords": os.getenv("IMAP_SUBJECT_INCLUDE_KEYWORDS", ""),
            "subject_exclude_keywords": os.getenv("IMAP_SUBJECT_EXCLUDE_KEYWORDS", ""),
        }
    )
    if not all([crawler.config.get("host"), crawler.config.get("username"), crawler.config.get("password")]):
        logger.warning("IMAP credentials are not configured; skipping HSBC email fetch.")
        return 0

    since_date = today - timedelta(days=1)
    emails = crawler.fetch_hsbc_emails(since_date)
    recorder = TradeRecorder()
    created_count = 0

    for raw_email in emails:
        try:
            parsed = crawler.parse_trade_email(raw_email)
        except ValueError as exc:
            logger.info("Skipping email during HSBC trade parsing: %s", exc)
            continue
        if is_trade_before_ingestion_start(parsed):
            logger.info("Skipping HSBC email trade before ingestion baseline: %s", parsed.get("trade_time"))
            continue
        try:
            _, created = recorder.record_trade(parsed)
        except ValueError as exc:
            logger.info("Skipping parsed HSBC trade during persistence: %s", exc)
            continue
        created_count += int(created)

    return created_count


@shared_task
def fetch_hsbc_email_trades() -> int:
    return run_hsbc_email_ingestion()
