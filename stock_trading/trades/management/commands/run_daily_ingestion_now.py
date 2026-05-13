from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand

from portfolio.tasks import refresh_market_price_snapshots
from trades.tasks import run_futu_ingestion, run_hsbc_email_ingestion, run_ths_ingestion


class Command(BaseCommand):
    help = "Run the daily THS, HSBC, and Futu ingestion flow immediately."

    def add_arguments(self, parser):
        parser.add_argument("--skip-ths", action="store_true", help="Skip THS ingestion.")
        parser.add_argument("--skip-hsbc", action="store_true", help="Skip HSBC email ingestion.")
        parser.add_argument("--skip-futu", action="store_true", help="Skip Futu ingestion.")
        parser.add_argument("--json", action="store_true", help="Print the summary as JSON.")
        parser.add_argument("--ths-bridge-python", default="", help="Override THS bridge python path.")
        parser.add_argument("--ths-window-title-keyword", default="", help="Override THS window title keyword.")

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        if options["ths_bridge_python"]:
            import os

            os.environ["THS_BRIDGE_PYTHON"] = options["ths_bridge_python"]
        if options["ths_window_title_keyword"]:
            import os

            os.environ["THS_WINDOW_TITLE_KEYWORD"] = options["ths_window_title_keyword"]

        summary = {}
        errors = {}
        if not options["skip_ths"]:
            try:
                summary["ths_created_count"] = int(run_ths_ingestion())
            except Exception as exc:
                errors["ths_error"] = str(exc)
        if not options["skip_hsbc"]:
            try:
                summary["hsbc_created_count"] = int(run_hsbc_email_ingestion())
            except Exception as exc:
                errors["hsbc_error"] = str(exc)
        if not options["skip_futu"]:
            try:
                summary["futu_created_count"] = int(run_futu_ingestion())
            except Exception as exc:
                errors["futu_error"] = str(exc)
        try:
            summary["market_snapshot"] = refresh_market_price_snapshots()
        except Exception as exc:
            errors["market_snapshot_error"] = str(exc)

        if options["json"]:
            self.stdout.write(json.dumps({**summary, **errors}, ensure_ascii=False, indent=2))
            return

        parts = []
        if "ths_created_count" in summary:
            parts.append(f"THS created {summary['ths_created_count']} trade(s)")
        if "hsbc_created_count" in summary:
            parts.append(f"HSBC created {summary['hsbc_created_count']} trade(s)")
        if "futu_created_count" in summary:
            parts.append(f"FUTU created {summary['futu_created_count']} trade(s)")
        if "market_snapshot" in summary:
            snapshot_summary = summary["market_snapshot"]
            if snapshot_summary.get("skipped"):
                parts.append(f"Market snapshot refresh skipped: {snapshot_summary.get('reason')}")
            else:
                parts.append(
                    f"Market snapshots refreshed for {snapshot_summary.get('securities', 0)} security(s)"
                )
        if "ths_error" in errors:
            parts.append(f"THS error: {errors['ths_error']}")
        if "hsbc_error" in errors:
            parts.append(f"HSBC error: {errors['hsbc_error']}")
        if "futu_error" in errors:
            parts.append(f"FUTU error: {errors['futu_error']}")
        if "market_snapshot_error" in errors:
            parts.append(f"Market snapshot error: {errors['market_snapshot_error']}")
        if errors:
            self.stdout.write(self.style.WARNING(" | ".join(parts) if parts else "No ingestion path executed."))
            return
        self.stdout.write(self.style.SUCCESS(" | ".join(parts) if parts else "No ingestion path executed."))
