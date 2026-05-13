from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from trades.models import TradeRecord


class FakeFutuCommandConnector:
    def __init__(self, config):
        self.config = config

    def fetch_trade_records(self, start=None, end=None):
        return [
            {
                "stock_code": "00700",
                "stock_name": "腾讯控股",
                "market": TradeRecord.Market.HK_STOCK,
                "direction": TradeRecord.Direction.BUY,
                "price": Decimal("320.50"),
                "quantity": 100,
                "trade_time": timezone.now(),
                "source": TradeRecord.Source.FUTU_API,
                "external_trade_id": "900000000123456789",
                "commission": Decimal("30.00"),
                "stamp_duty": Decimal("100.00"),
                "other_fees": Decimal("27.70"),
                "fee_details": [{"fee_name": "Commission", "fee_amount": "30.00"}],
            }
        ]


@pytest.mark.django_db
def test_futu_management_command_persists_trades(capsys):
    with patch("trades.management.commands.fetch_futu_trades_now.FutuConnector", FakeFutuCommandConnector):
        call_command(
            "fetch_futu_trades_now",
            host="127.0.0.1",
            port=11111,
            acc_id=101,
        )

    captured = capsys.readouterr()
    assert "created 1 new TradeRecord row" in captured.out
    assert TradeRecord.objects.filter(source=TradeRecord.Source.FUTU_API).count() == 1


@pytest.mark.django_db
def test_futu_management_command_dry_run_outputs_json(tmp_path, capsys):
    output_file = tmp_path / "futu_payload.json"
    with patch("trades.management.commands.fetch_futu_trades_now.FutuConnector", FakeFutuCommandConnector):
        call_command(
            "fetch_futu_trades_now",
            dry_run=True,
            json=True,
            output_file=str(output_file),
            host="127.0.0.1",
            port=11111,
            acc_id=101,
        )

    captured = capsys.readouterr()
    assert '"stock_code": "00700"' in captured.out
    assert "dry-run only" in captured.out
    payload = json.loads(Path(output_file).read_text(encoding="utf-8"))
    assert payload[0]["external_trade_id"] == "900000000123456789"
    assert TradeRecord.objects.count() == 0
