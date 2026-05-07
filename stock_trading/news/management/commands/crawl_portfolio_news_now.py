from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand

from news.tasks import crawl_portfolio_news


class Command(BaseCommand):
    help = "Crawl the configured news sources for all active portfolio positions."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print a JSON summary.")

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        created_count = int(crawl_portfolio_news())
        summary = {"created_count": created_count}

        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        self.stdout.write(self.style.SUCCESS(f"Crawled portfolio news; created {created_count} new NewsItem row(s)."))
