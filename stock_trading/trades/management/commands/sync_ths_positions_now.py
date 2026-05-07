from __future__ import annotations

import json
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from portfolio.services.portfolio_manager import PortfolioManager
from trades.models import TradeRecord
from trades.services.ths_connector import THSConnector


class Command(BaseCommand):
    help = "Sync current THS positions into the backend Position table."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print normalized positions without saving.")
        parser.add_argument("--json", action="store_true", help="Print normalized position payload as JSON.")
        parser.add_argument("--exe-path", default="", help="Override THS_EXE_PATH.")
        parser.add_argument("--bridge-python", default="", help="Override THS_BRIDGE_PYTHON.")
        parser.add_argument(
            "--window-title-keyword",
            default="",
            help="Override THS_WINDOW_TITLE_KEYWORD.",
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
            }
        )
        positions = connector.fetch_positions()

        if options["json"]:
            self.stdout.write(json.dumps(positions, ensure_ascii=False, indent=2, default=str))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Fetched {len(positions)} THS position(s); dry-run only."))
            return

        synced = PortfolioManager().sync_position_snapshots(positions, TradeRecord.Market.A_STOCK)
        self.stdout.write(self.style.SUCCESS(f"Synced {len(synced)} THS position(s)."))
