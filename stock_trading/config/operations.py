from __future__ import annotations

import os

from news.models import NewsItem
from news.tasks import crawl_portfolio_news, push_news_digest, push_notification
from portfolio.services.portfolio_manager import PortfolioManager
from trades.models import TradeRecord
from trades.services.ths_connector import THSConnector
from trades.tasks import run_hsbc_email_ingestion, run_ths_ingestion


def execute_ths_ingestion() -> dict:
    return {"created_count": int(run_ths_ingestion())}


def execute_hsbc_ingestion() -> dict:
    return {"created_count": int(run_hsbc_email_ingestion())}


def execute_daily_ingestion(skip_ths: bool = False, skip_hsbc: bool = False) -> dict:
    summary: dict[str, int | str] = {}

    if not skip_ths:
        try:
            summary["ths_created_count"] = int(run_ths_ingestion())
        except Exception as exc:  # pragma: no cover - exercised by API tests
            summary["ths_error"] = str(exc)

    if not skip_hsbc:
        try:
            summary["hsbc_created_count"] = int(run_hsbc_email_ingestion())
        except Exception as exc:  # pragma: no cover - exercised by API tests
            summary["hsbc_error"] = str(exc)

    return summary


def execute_sync_ths_positions(
    exe_path: str = "",
    bridge_python: str = "",
    window_title_keyword: str = "",
) -> dict:
    resolved_exe_path = exe_path.strip() or os.getenv("THS_EXE_PATH", "").strip()
    resolved_bridge_python = bridge_python.strip() or os.getenv("THS_BRIDGE_PYTHON", "").strip()
    resolved_window_title_keyword = (
        window_title_keyword.strip() or os.getenv("THS_WINDOW_TITLE_KEYWORD", "股票交易系统")
    )

    if not resolved_exe_path and not resolved_bridge_python:
        raise FileNotFoundError("THS_EXE_PATH or THS_BRIDGE_PYTHON must be configured.")

    connector = THSConnector(
        {
            "exe_path": resolved_exe_path or None,
            "client_type": os.getenv("THS_CLIENT_TYPE", "ths"),
            "bridge_python": resolved_bridge_python or None,
            "window_title_keyword": resolved_window_title_keyword,
        }
    )
    positions = connector.fetch_positions()
    synced = PortfolioManager().sync_position_snapshots(positions, TradeRecord.Market.A_STOCK)
    return {"fetched_count": len(positions), "synced_count": len(synced)}


def execute_news_crawl() -> dict:
    return {"created_count": int(crawl_portfolio_news())}


def execute_push_pending_notifications(limit: int = 20) -> dict:
    queryset = NewsItem.objects.filter(pushed=False).order_by("-published_at")[:limit]
    processed = 0
    success = 0
    failed = 0

    for news in queryset:
        processed += 1
        result = bool(push_notification(news.id))
        if result:
            success += 1
        else:
            failed += 1

    return {"processed": processed, "success": success, "failed": failed}


def execute_push_digest() -> dict:
    return {"success": bool(push_news_digest())}
