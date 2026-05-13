from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from trades.services.futu_connector import FutuConnector
from trades.services.trade_recorder import TradeRecorder


class Command(BaseCommand):
    help = "Fetch Futu Hong Kong trade records and optionally persist them into TradeRecord."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and print normalized trades without saving them.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print normalized trade payload as JSON.",
        )
        parser.add_argument(
            "--output-file",
            default="",
            help="Write normalized trades to a UTF-8 JSON file.",
        )
        parser.add_argument(
            "--since-days",
            type=int,
            default=1,
            help="Fetch orders since N days ago. Default: 1",
        )
        parser.add_argument("--host", default="", help="Override FUTU_HOST.")
        parser.add_argument("--port", type=int, default=0, help="Override FUTU_PORT.")
        parser.add_argument("--acc-id", dest="acc_id", type=int, default=0, help="Override FUTU_ACC_ID.")
        parser.add_argument("--security-firm", default="", help="Override FUTU_SECURITY_FIRM.")

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        host = options["host"].strip() or os.getenv("FUTU_HOST", "").strip()
        port = options["port"] or int(os.getenv("FUTU_PORT", "11111"))
        acc_id = options["acc_id"] or int(os.getenv("FUTU_ACC_ID", "0"))
        if not host or not acc_id:
            raise CommandError("FUTU_HOST and FUTU_ACC_ID must be configured.")

        connector = FutuConnector(
            {
                "host": host,
                "port": port,
                "acc_id": acc_id,
                "security_firm": options["security_firm"].strip() or os.getenv("FUTU_SECURITY_FIRM", "").strip(),
            }
        )
        since_date = timezone.localdate() - timedelta(days=max(options["since_days"], 0))
        records = connector.fetch_trade_records(start=since_date, end=timezone.localdate())
        serialized = [self._serialize_trade(item) for item in records]

        output_file = options["output_file"].strip()
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote normalized Futu payload to {output_path}"))

        if options["json"]:
            self.stdout.write(json.dumps(serialized, ensure_ascii=False, indent=2))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Fetched {len(records)} Futu trade(s); dry-run only."))
            return

        recorder = TradeRecorder()
        created_count = 0
        for record in records:
            _, created = recorder.record_trade(record)
            created_count += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Fetched {len(records)} Futu trade(s); created {created_count} new TradeRecord row(s)."
            )
        )

    def _serialize_trade(self, trade: dict) -> dict:
        serialized = dict(trade)
        if "trade_time" in serialized and hasattr(serialized["trade_time"], "isoformat"):
            serialized["trade_time"] = serialized["trade_time"].isoformat()
        for key in ("price", "commission", "stamp_duty", "other_fees"):
            if key in serialized:
                serialized[key] = str(serialized[key])
        return serialized
