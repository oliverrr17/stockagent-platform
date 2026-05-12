from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command

from portfolio.models import Position
from trades.models import TradeRecord


class FakeTHSConnector:
    def __init__(self, config):
        self.config = config

    def fetch_positions(self):
        return [
            {
                "stock_code": "603063",
                "stock_name": "禾望电气",
                "market": TradeRecord.Market.A_STOCK,
                "quantity": 100,
                "cost_price": Decimal("41.4300"),
                "weighted_avg_cost": Decimal("41.4300"),
                "total_invested": Decimal("4143.0000"),
                "realized_pnl": Decimal("0"),
                "status": "ACTIVE",
            }
        ]


@pytest.mark.django_db
def test_sync_ths_positions_command_dry_run(capsys):
    with patch("trades.management.commands.sync_ths_positions_now.THSConnector", FakeTHSConnector):
        call_command("sync_ths_positions_now", dry_run=True, json=True, bridge_python=r"C:\Python38\python.exe")

    captured = capsys.readouterr()
    assert '"stock_code": "603063"' in captured.out
    assert "dry-run only" in captured.out
    assert Position.objects.count() == 0


@pytest.mark.django_db
def test_sync_ths_positions_command_persists_snapshot(capsys):
    with patch("trades.management.commands.sync_ths_positions_now.THSConnector", FakeTHSConnector):
        call_command("sync_ths_positions_now", bridge_python=r"C:\Python38\python.exe")

    captured = capsys.readouterr()
    assert "Synced 1 THS position" in captured.out
    position = Position.objects.get(stock_code="603063")
    assert position.quantity == 100
    assert position.market == TradeRecord.Market.A_STOCK


@pytest.mark.django_db
def test_sync_ths_positions_command_supports_macos_backend_without_windows_paths(monkeypatch, capsys):
    class FakeMacConnector(FakeTHSConnector):
        def test_connection(self):
            return True

    monkeypatch.setenv("THS_BACKEND", "macos_ths_local")

    with patch("trades.management.commands.sync_ths_positions_now.THSConnector", FakeMacConnector):
        call_command("sync_ths_positions_now", dry_run=True, json=True)

    captured = capsys.readouterr()
    assert '"stock_code": "603063"' in captured.out
    assert "dry-run only" in captured.out
