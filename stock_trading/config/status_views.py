from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .operations import (
    execute_daily_ingestion,
    execute_futu_ingestion,
    execute_hsbc_ingestion,
    execute_news_crawl,
    execute_push_digest,
    execute_push_pending_notifications,
    execute_sync_ths_positions,
    execute_ths_ingestion,
)
from news.models import NewsItem, NotificationLog
from portfolio.models import Position
from trades.models import TradeRecord


class OperationsStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        recent_logs = self._recent_scheduler_logs()
        return Response(
            {
                "counts": {
                    "active_positions": Position.objects.filter(status=Position.Status.ACTIVE, quantity__gt=0).count(),
                    "trades_total": TradeRecord.objects.count(),
                    "news_total": NewsItem.objects.count(),
                    "news_pending": NewsItem.objects.filter(pushed=False).count(),
                    "news_pushed": NewsItem.objects.filter(pushed=True).count(),
                    "notification_logs": NotificationLog.objects.count(),
                },
                "scheduler": {
                    "ths": f"{self._env('THS_FETCH_HOUR', '16')}:{self._env('THS_FETCH_MINUTE', '10').zfill(2)}",
                    "hsbc": f"{self._env('HSBC_FETCH_HOUR', '18')}:{self._env('HSBC_FETCH_MINUTE', '30').zfill(2)}",
                    "futu": f"{self._env('FUTU_FETCH_HOUR', '18')}:{self._env('FUTU_FETCH_MINUTE', '35').zfill(2)}",
                    "news_fetch": f"{self._env('NEWS_FETCH_HOURS', '8,9,10,11,12,13,14,15,16,17,18,19,20,21,22')}:{self._env('NEWS_FETCH_MINUTE', '0').zfill(2)}",
                    "news_digest": f"{self._env('NEWS_DIGEST_HOUR', '18')}:{self._env('NEWS_DIGEST_MINUTE', '35').zfill(2)}",
                },
                "alerts": self._build_alerts(recent_logs),
                "recent_logs": recent_logs,
            }
        )

    def _env(self, key: str, default: str):
        return os.getenv(key, default)

    def _recent_scheduler_logs(self):
        scheduler_dir = Path(settings.PROJECT_ROOT) / "output" / "scheduler"
        if not scheduler_dir.exists():
            return []

        logs = []
        for path in sorted(scheduler_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            logs.append(
                {
                    "name": path.name,
                    "updated_at": path.stat().st_mtime,
                    "last_line": lines[-1] if lines else "",
                    "preview": lines[-8:],
                }
            )
        return logs

    def _build_alerts(self, recent_logs: list[dict]):
        alerts = []
        if NewsItem.objects.filter(pushed=False).count() > 0:
            alerts.append(
                {
                    "severity": "warning",
                    "title": "存在未推送新闻",
                    "message": f"当前仍有 {NewsItem.objects.filter(pushed=False).count()} 条新闻待处理。",
                }
            )

        for item in recent_logs[:2]:
            line = (item.get("last_line") or "").lower()
            if "error" in line or "failed" in line or "warning" in line:
                alerts.append(
                    {
                        "severity": "error",
                        "title": item["name"],
                        "message": item.get("last_line") or "最近日志包含异常输出。",
                    }
                )

        return alerts


class OperationsActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, action: str):
        payload = request.data if isinstance(request.data, dict) else {}

        try:
            if action == "run-ths":
                result = execute_ths_ingestion()
            elif action == "run-hsbc":
                result = execute_hsbc_ingestion()
            elif action == "run-futu":
                result = execute_futu_ingestion()
            elif action == "run-daily":
                result = execute_daily_ingestion(
                    skip_ths=bool(payload.get("skip_ths", False)),
                    skip_hsbc=bool(payload.get("skip_hsbc", False)),
                    skip_futu=bool(payload.get("skip_futu", False)),
                )
            elif action == "sync-ths-positions":
                result = execute_sync_ths_positions(
                    exe_path=str(payload.get("exe_path", "")),
                    bridge_python=str(payload.get("bridge_python", "")),
                    window_title_keyword=str(payload.get("window_title_keyword", "")),
                )
            elif action == "crawl-news":
                result = execute_news_crawl()
            elif action == "push-news":
                result = execute_push_pending_notifications(int(payload.get("limit", 20)))
            elif action == "push-digest":
                result = execute_push_digest()
            else:
                raise ValidationError({"detail": f"Unsupported operation action: {action}"})
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        return Response({"action": action, **result})
