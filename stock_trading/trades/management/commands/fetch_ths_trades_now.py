from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from trades.services.ths_connector import THSConnector
from trades.services.trade_recorder import TradeRecorder


class Command(BaseCommand):
    help = "Fetch today's THS trades and optionally persist them into TradeRecord."

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
            "--exe-path",
            default="",
            help="Override THS_EXE_PATH for this run.",
        )
        parser.add_argument(
            "--bridge-python",
            default="",
            help="Override THS_BRIDGE_PYTHON for this run.",
        )
        parser.add_argument(
            "--window-title-keyword",
            default="",
            help="Override THS_WINDOW_TITLE_KEYWORD for this run.",
        )
        parser.add_argument(
            "--output-file",
            default="",
            help="Write normalized trades to a UTF-8 JSON file.",
        )

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        exe_path = options["exe_path"].strip() or os.getenv("THS_EXE_PATH", "").strip()
        bridge_python = options["bridge_python"].strip() or os.getenv("THS_BRIDGE_PYTHON", "").strip()
        window_title_keyword = (
            options["window_title_keyword"].strip()
            or os.getenv("THS_WINDOW_TITLE_KEYWORD", "股票交易系统")
        )

        if not exe_path and not bridge_python:
            raise CommandError("THS_EXE_PATH or THS_BRIDGE_PYTHON must be configured.")

        connector = THSConnector(
            {
                "exe_path": exe_path or None,
                "client_type": os.getenv("THS_CLIENT_TYPE", "ths"),
                "bridge_python": bridge_python or None,
                "window_title_keyword": window_title_keyword,
                "trade_date": timezone.localdate(),
            }
        )

        trades = connector.fetch_today_trades()
        serialized_trades = [self._serialize_trade(trade) for trade in trades]

        output_file = options["output_file"].strip()
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(serialized_trades, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(self.style.SUCCESS(f"Wrote normalized THS payload to {output_path}"))

        if options["json"]:
            self.stdout.write(json.dumps(serialized_trades, ensure_ascii=False, indent=2))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Fetched {len(trades)} THS trade(s); dry-run only."))
            return

        recorder = TradeRecorder()
        created_count = 0
        for trade in trades:
            _, created = recorder.record_trade(trade)
            created_count += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Fetched {len(trades)} THS trade(s); created {created_count} new TradeRecord row(s)."
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
