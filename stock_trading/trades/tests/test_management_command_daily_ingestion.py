from unittest.mock import patch

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_daily_ingestion_command_runs_both_paths(capsys):
    with (
        patch("trades.management.commands.run_daily_ingestion_now.run_ths_ingestion", return_value=2),
        patch("trades.management.commands.run_daily_ingestion_now.run_hsbc_email_ingestion", return_value=1),
        patch("trades.management.commands.run_daily_ingestion_now.refresh_market_price_snapshots", return_value={"securities": 3, "snapshots_written": 6}),
    ):
        call_command("run_daily_ingestion_now")

    captured = capsys.readouterr()
    assert "THS created 2 trade(s)" in captured.out
    assert "HSBC created 1 trade(s)" in captured.out
    assert "Market snapshots refreshed for 3 security(s)" in captured.out


@pytest.mark.django_db
def test_daily_ingestion_command_can_skip_paths_and_emit_json(capsys):
    with (
        patch("trades.management.commands.run_daily_ingestion_now.run_ths_ingestion", return_value=2),
        patch("trades.management.commands.run_daily_ingestion_now.run_hsbc_email_ingestion", return_value=1),
        patch("trades.management.commands.run_daily_ingestion_now.refresh_market_price_snapshots", return_value={"securities": 3, "snapshots_written": 6}),
    ):
        call_command("run_daily_ingestion_now", skip_ths=True, json=True)

    captured = capsys.readouterr()
    assert '"hsbc_created_count": 1' in captured.out
    assert '"market_snapshot": {' in captured.out
    assert "ths_created_count" not in captured.out


@pytest.mark.django_db
def test_daily_ingestion_command_reports_partial_failure(capsys):
    with (
        patch("trades.management.commands.run_daily_ingestion_now.run_ths_ingestion", side_effect=FileNotFoundError("bridge missing")),
        patch("trades.management.commands.run_daily_ingestion_now.run_hsbc_email_ingestion", return_value=1),
        patch("trades.management.commands.run_daily_ingestion_now.refresh_market_price_snapshots", return_value={"securities": 3, "snapshots_written": 6}),
    ):
        call_command("run_daily_ingestion_now", json=True)

    captured = capsys.readouterr()
    assert '"hsbc_created_count": 1' in captured.out
    assert '"ths_error": "bridge missing"' in captured.out
    assert '"market_snapshot": {' in captured.out
