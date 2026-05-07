from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from trades.ingestion_policy import is_trade_before_ingestion_start
from trades.services.email_crawler import EmailCrawler
from trades.services.trade_recorder import TradeRecorder


class Command(BaseCommand):
    help = "Fetch HSBC trade confirmation emails, parse them, and optionally persist them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--test-connection",
            action="store_true",
            help="Only test IMAP connectivity and exit.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and parse emails without saving TradeRecord rows.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print parsed trade payloads as JSON.",
        )
        parser.add_argument(
            "--output-file",
            default="",
            help="Write parsed trades to a UTF-8 JSON file.",
        )
        parser.add_argument(
            "--since-days",
            type=int,
            default=1,
            help="Fetch emails since N days ago. Default: 1",
        )
        parser.add_argument(
            "--subject-keyword",
            action="append",
            default=[],
            help="Filter server-side by a specific SUBJECT keyword. Repeatable.",
        )
        parser.add_argument("--host", default="", help="Override IMAP_HOST.")
        parser.add_argument("--port", type=int, default=0, help="Override IMAP_PORT.")
        parser.add_argument("--username", default="", help="Override IMAP_USERNAME.")
        parser.add_argument("--password", default="", help="Override IMAP_PASSWORD.")
        parser.add_argument("--mailbox", default="", help="Override IMAP_MAILBOX.")
        parser.add_argument("--sender-keyword", default="", help="Override IMAP_SENDER_KEYWORD.")

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        crawler = EmailCrawler(
            {
                "host": options["host"].strip() or os.getenv("IMAP_HOST", "").strip(),
                "port": options["port"] or int(os.getenv("IMAP_PORT", "993")),
                "username": options["username"].strip() or os.getenv("IMAP_USERNAME", "").strip(),
                "password": options["password"].strip() or os.getenv("IMAP_PASSWORD", "").strip(),
                "mailbox": options["mailbox"].strip() or os.getenv("IMAP_MAILBOX", "INBOX").strip(),
                "sender_keyword": options["sender_keyword"].strip()
                or os.getenv("IMAP_SENDER_KEYWORD", "hsbc").strip(),
                "sender_filters": os.getenv("IMAP_SENDER_FILTERS", "").strip(),
                "subject_include_keywords": os.getenv("IMAP_SUBJECT_INCLUDE_KEYWORDS", "").strip(),
                "subject_exclude_keywords": os.getenv("IMAP_SUBJECT_EXCLUDE_KEYWORDS", "").strip(),
                "subject_search_terms": options["subject_keyword"],
            }
        )
        if not all([crawler.config.get("host"), crawler.config.get("username"), crawler.config.get("password")]):
            raise CommandError("IMAP_HOST, IMAP_USERNAME and IMAP_PASSWORD must be configured.")

        try:
            if options["test_connection"]:
                crawler.test_connection()
                self.stdout.write(self.style.SUCCESS("HSBC IMAP connection succeeded."))
                return

            since_date = timezone.localdate() - timedelta(days=max(options["since_days"], 0))
            emails = crawler.fetch_hsbc_emails(since_date)
            parsed_trades = []
            skipped_count = 0
            for raw_email in emails:
                try:
                    parsed = crawler.parse_trade_email(raw_email)
                except ValueError:
                    skipped_count += 1
                    continue
                if is_trade_before_ingestion_start(parsed):
                    skipped_count += 1
                    continue
                parsed_trades.append(parsed)

            serialized = [self._serialize_trade(item) for item in parsed_trades]
            output_file = options["output_file"].strip()
            if output_file:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
                self.stdout.write(self.style.SUCCESS(f"Wrote parsed HSBC payload to {output_path}"))

            if options["json"]:
                self.stdout.write(json.dumps(serialized, ensure_ascii=False, indent=2))

            if options["dry_run"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"Fetched {len(emails)} email(s); parsed {len(parsed_trades)} trade(s); skipped {skipped_count}; dry-run only."
                    )
                )
                return

            recorder = TradeRecorder()
            created_count = 0
            for trade in parsed_trades:
                try:
                    _, created = recorder.record_trade(trade)
                except ValueError:
                    skipped_count += 1
                    continue
                created_count += int(created)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Fetched {len(emails)} email(s); parsed {len(parsed_trades)} trade(s); "
                    f"skipped {skipped_count}; created {created_count} new TradeRecord row(s)."
                )
            )
        finally:
            crawler.close()

    def _serialize_trade(self, trade: dict) -> dict:
        serialized = dict(trade)
        if "trade_time" in serialized and hasattr(serialized["trade_time"], "isoformat"):
            serialized["trade_time"] = serialized["trade_time"].isoformat()
        for key in ("price", "commission", "stamp_duty", "other_fees"):
            if key in serialized:
                serialized[key] = str(serialized[key])
        return serialized
