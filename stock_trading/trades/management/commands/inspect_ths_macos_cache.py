from __future__ import annotations

import json
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from trades.services.ths_connector import THSConnector


class Command(BaseCommand):
    help = "Inspect structured cache surfaces under the TongHuaShun macOS container."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Maximum number of recent manifest keys to show.")
        parser.add_argument("--json", action="store_true", help="Print the inspection report as JSON.")
        parser.add_argument(
            "--related-only",
            action="store_true",
            help="Only include trade/position-related candidate payloads in the report.",
        )

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        backend = os.getenv("THS_BACKEND", THSConnector.BACKEND_MACOS_LOCAL).strip()
        connector = THSConnector({"backend": backend})
        if connector.backend != THSConnector.BACKEND_MACOS_LOCAL:
            raise CommandError("inspect_ths_macos_cache only supports THS_BACKEND=macos_ths_local.")

        report = connector.macos_backend.inspect_cache(
            limit=int(options["limit"]),
            related_only=bool(options["related_only"]),
        )
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        self.stdout.write(f"THS macOS cache available: {report['available']}")
        if report.get("unavailable_reason"):
            self.stdout.write(f"Reason: {report['unavailable_reason']}")
        self.stdout.write(f"App path: {report['app_path']}")
        self.stdout.write(f"Container path: {report['container_path']}")
        self.stdout.write(f"Manifest path: {report['manifest_path']}")
        self.stdout.write("Recent manifest keys:")
        for key in report["recent_manifest_keys"]:
            self.stdout.write(f"  - {key}")
        self.stdout.write("Candidate payloads:")
        for item in report["candidate_payloads"]:
            shape = json.dumps(item["payload_shape"], ensure_ascii=False)
            self.stdout.write(
                f"  - [{item['source']}] trade_rows={item['trade_rows']} "
                f"position_rows={item['position_rows']} key={item['key']}"
            )
            self.stdout.write(f"    shape={shape}")
