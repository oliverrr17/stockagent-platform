from datetime import datetime, timedelta
from decimal import Decimal
import json
import sys

from django.utils import timezone
import pytest

from trades.models import TradeRecord
from trades.services.ths_connector import THSConnector


class FakeTHSUser:
    def __init__(self, today_trades=None, position=None, balance=None):
        self.today_trades = today_trades or []
        self.position = position or []
        self.balance = balance or []
        self.connected_path = None

    def connect(self, exe_path):
        self.connected_path = exe_path


def test_connect_uses_injected_factory_and_exe_path():
    fake_user = FakeTHSUser()
    connector = THSConnector(
        {
            "exe_path": r"C:\ths\xiadan.exe",
            "client_factory": lambda: fake_user,
        }
    )

    assert connector.connect() is True
    assert fake_user.connected_path == r"C:\ths\xiadan.exe"


def test_fetch_today_trades_normalizes_easytrader_payload():
    fake_user = FakeTHSUser(
        today_trades=[
            {
                "证券代码": "600519",
                "证券名称": "贵州茅台",
                "买卖标志": "证券买入",
                "成交价格": "1500.23",
                "成交数量": "10",
                "成交时间": "14:35:12",
            }
        ]
    )
    trade_date = timezone.localdate()
    connector = THSConnector(
        {
            "user": fake_user,
            "exe_path": r"C:\ths\xiadan.exe",
            "trade_date": trade_date,
        }
    )

    trades = connector.fetch_today_trades()

    assert len(trades) == 1
    trade = trades[0]
    assert trade["stock_code"] == "600519"
    assert trade["stock_name"] == "贵州茅台"
    assert trade["market"] == TradeRecord.Market.A_STOCK
    assert trade["direction"] == TradeRecord.Direction.BUY
    assert trade["price"] == Decimal("1500.23")
    assert trade["quantity"] == 10
    assert trade["trade_time"].date() == trade_date
    assert trade["source"] == TradeRecord.Source.THS


def test_fetch_today_trades_normalizes_real_today_trades_sample():
    fake_user = FakeTHSUser(
        today_trades=[
            {
                "成交时间": "14:04:34",
                "证券代码": "603063",
                "证券名称": "禾望电气",
                "操作": "证券卖出",
                "成交数量": 100.0,
                "成交均价": 41.43,
                "成交金额": 4143.0,
                "合同编号": "943703",
                "成交编号": 53003050,
                "Unnamed: 9": "",
            }
        ]
    )
    trade_date = timezone.localdate()
    connector = THSConnector({"user": fake_user, "trade_date": trade_date})

    trades = connector.fetch_today_trades()

    assert len(trades) == 1
    assert trades[0]["stock_code"] == "603063"
    assert trades[0]["stock_name"] == "禾望电气"
    assert trades[0]["direction"] == TradeRecord.Direction.SELL
    assert trades[0]["price"] == Decimal("41.43")
    assert trades[0]["quantity"] == 100
    assert trades[0]["trade_time"].date() == trade_date


def test_fetch_trade_records_returns_empty_when_range_excludes_today():
    fake_user = FakeTHSUser(
        today_trades=[
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "entrust_bs": "买入",
                "business_price": "1500.23",
                "business_amount": "10",
                "business_time": "14:35:12",
            }
        ]
    )
    connector = THSConnector({"user": fake_user, "exe_path": r"C:\ths\xiadan.exe"})
    past_date = timezone.localdate() - timedelta(days=1)

    trades = connector.fetch_trade_records(past_date, past_date)

    assert trades == []


def test_fetch_trade_records_supports_configured_mock_records():
    trade_time = timezone.make_aware(datetime(2026, 4, 21, 14, 35, 12), timezone.get_current_timezone())
    connector = THSConnector(
        {
            "records": [
                {
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "market": TradeRecord.Market.A_STOCK,
                    "direction": TradeRecord.Direction.BUY,
                    "price": Decimal("1500.23"),
                    "quantity": 10,
                    "trade_time": trade_time,
                    "source": TradeRecord.Source.THS,
                }
            ]
        }
    )

    trades = connector.fetch_trade_records(trade_time.date(), trade_time.date())

    assert len(trades) == 1
    assert trades[0]["stock_code"] == "600519"


def test_bridge_mode_uses_external_payload_runner():
    raw_payload = json.dumps(
        [
            {
                "成交时间": "14:04:34",
                "证券代码": "603063",
                "证券名称": "禾望电气",
                "操作": "证券卖出",
                "成交数量": 100.0,
                "成交均价": 41.43,
            }
        ],
        ensure_ascii=False,
    )

    def fake_bridge_runner(**kwargs):
        if kwargs["mode"] == "probe":
            return {"ok": True}
        return json.loads(raw_payload)

    connector = THSConnector(
        {
            "bridge_python": r"C:\Users\demo\AppData\Local\Programs\Python\Python38-32\python.exe",
            "bridge_runner": fake_bridge_runner,
            "trade_date": timezone.localdate(),
        }
    )

    assert connector.test_connection() is True
    trades = connector.fetch_today_trades()
    assert len(trades) == 1
    assert trades[0]["stock_code"] == "603063"
    assert trades[0]["direction"] == TradeRecord.Direction.SELL


def test_fetch_positions_normalizes_real_position_snapshot_shape():
    fake_user = FakeTHSUser(
        position=[
            {
                "证券代码": "603063",
                "证券名称": "禾望电气",
                "当前拥股数": 300,
                "成本价": 39.201,
                "交易市场": "上海Ａ股",
            }
        ]
    )
    connector = THSConnector({"user": fake_user})

    positions = connector.fetch_positions()

    assert len(positions) == 1
    assert positions[0]["stock_code"] == "603063"
    assert positions[0]["stock_name"] == "禾望电气"
    assert positions[0]["quantity"] == 300
    assert positions[0]["weighted_avg_cost"] == Decimal("39.201")
    assert positions[0]["market"] == TradeRecord.Market.A_STOCK


def test_bridge_mode_decodes_gbk_stderr_messages(tmp_path):
    bridge_script = tmp_path / "bridge_failure.py"
    bridge_script.write_text(
        "import sys\n"
        "sys.stderr.buffer.write('桥接失败'.encode('gbk'))\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )

    connector = THSConnector(
        {
            "bridge_python": sys.executable,
            "bridge_script": str(bridge_script),
        }
    )

    with pytest.raises(RuntimeError, match="桥接失败"):
        connector.fetch_today_trades()
