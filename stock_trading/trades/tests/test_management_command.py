from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from trades.models import TradeRecord


class FakeConnector:
    def __init__(self, config):
        self.config = config

    def fetch_today_trades(self):
        return [
            {
                "stock_code": "603063",
                "stock_name": "禾望电气",
                "market": TradeRecord.Market.A_STOCK,
                "direction": TradeRecord.Direction.BUY,
                "price": Decimal("41.43"),
                "quantity": 100,
                "trade_time": timezone.now(),
                "source": TradeRecord.Source.THS,
                "commission": Decimal("0"),
                "stamp_duty": Decimal("0"),
                "other_fees": Decimal("0"),
            }
        ]


@pytest.mark.django_db
def test_management_command_persists_trades(capsys):
    with patch("trades.management.commands.fetch_ths_trades_now.THSConnector", FakeConnector):
        call_command(
            "fetch_ths_trades_now",
            exe_path=r"D:\同花顺\xiadan.exe",
        )

    captured = capsys.readouterr()
    assert "created 1 new TradeRecord row" in captured.out
    assert TradeRecord.objects.count() == 1


@pytest.mark.django_db
def test_management_command_dry_run_does_not_persist(capsys):
    with patch("trades.management.commands.fetch_ths_trades_now.THSConnector", FakeConnector):
        call_command(
            "fetch_ths_trades_now",
            exe_path=r"D:\同花顺\xiadan.exe",
            dry_run=True,
            json=True,
        )

    captured = capsys.readouterr()
    assert '"stock_code": "603063"' in captured.out
    assert "dry-run only" in captured.out
    assert TradeRecord.objects.count() == 0


@pytest.mark.django_db
def test_management_command_writes_utf8_json_file(tmp_path, capsys):
    output_file = tmp_path / "ths_payload.json"
    with patch("trades.management.commands.fetch_ths_trades_now.THSConnector", FakeConnector):
        call_command(
            "fetch_ths_trades_now",
            exe_path=r"D:\同花顺\xiadan.exe",
            dry_run=True,
            output_file=str(output_file),
        )

    captured = capsys.readouterr()
    assert "Wrote normalized THS payload" in captured.out
    payload = json.loads(Path(output_file).read_text(encoding="utf-8"))
    assert payload[0]["stock_name"] == "禾望电气"


@pytest.mark.django_db
def test_management_command_supports_macos_backend_without_windows_paths(monkeypatch, capsys):
    class FakeMacConnector(FakeConnector):
        def test_connection(self):
            return True

    monkeypatch.setenv("THS_BACKEND", "macos_ths_local")

    with patch("trades.management.commands.fetch_ths_trades_now.THSConnector", FakeMacConnector):
        call_command(
            "fetch_ths_trades_now",
            dry_run=True,
            json=True,
        )

    captured = capsys.readouterr()
    assert '"stock_code": "603063"' in captured.out
    assert "dry-run only" in captured.out
