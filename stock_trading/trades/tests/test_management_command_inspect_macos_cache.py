import json
from unittest.mock import patch

import pytest
from django.core.management import call_command


class FakeMacConnector:
    BACKEND_MACOS_LOCAL = "macos_ths_local"

    def __init__(self, config):
        self.backend = "macos_ths_local"
        self.macos_backend = self

    def inspect_cache(self, limit=50, related_only=False):
        return {
            "available": True,
            "unavailable_reason": None,
            "app_path": "/Applications/同花顺.app",
            "container_path": "/tmp/container",
            "manifest_path": "/tmp/container/manifest.sqlite",
            "recent_manifest_keys": ["https://example.com/today_order"],
            "candidate_payloads": [
                {
                    "source": "manifest_cache",
                    "key": "https://example.com/today_order",
                    "priority": 0,
                    "trade_rows": 1,
                    "position_rows": 0,
                    "payload_shape": {"type": "dict", "data_length": 1},
                }
            ],
        }


def test_inspect_ths_macos_cache_command_outputs_json(capsys):
    with patch("trades.management.commands.inspect_ths_macos_cache.THSConnector", FakeMacConnector):
        call_command("inspect_ths_macos_cache", json=True, limit=10)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["available"] is True
    assert payload["candidate_payloads"][0]["trade_rows"] == 1


@pytest.mark.django_db
def test_inspect_ths_macos_cache_command_outputs_text(capsys):
    with patch("trades.management.commands.inspect_ths_macos_cache.THSConnector", FakeMacConnector):
        call_command("inspect_ths_macos_cache", limit=10)

    captured = capsys.readouterr()
    assert "THS macOS cache available: True" in captured.out
    assert "trade_rows=1" in captured.out
