from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand

from news.models import NewsItem
from news.tasks import push_news_digest, push_notification


class Command(BaseCommand):
    help = "Push immediate P1 news notifications or send a P2 digest."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="Maximum number of news items to process.")
        parser.add_argument("--digest", action="store_true", help="Send one digest email for all pending P2 items.")
        parser.add_argument("--json", action="store_true", help="Print a JSON summary.")

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        if options["digest"]:
            result = bool(push_news_digest())
            summary = {"mode": "digest", "success": result}
            if options["json"]:
                self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
                return
            self.stdout.write(self.style.SUCCESS(str(summary)))
            return

        queryset = NewsItem.objects.filter(pushed=False).order_by("-published_at")[: options["limit"]]
        total = 0
        success = 0
        failed = 0

        for news in queryset:
            total += 1
            result = bool(push_notification(news.id))
            if result:
                success += 1
            else:
                failed += 1

        summary = {"mode": "immediate", "processed": total, "success": success, "failed": failed}
        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        self.stdout.write(self.style.SUCCESS(str(summary)))
