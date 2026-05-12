from datetime import datetime, timedelta
from decimal import Decimal
import json
import plistlib
import sqlite3
import sys

from django.utils import timezone
import pytest

from trades.models import TradeRecord
from trades.services.ths_connector import THSConnector
from trades.services.ths_macos_local import NSKeyedArchiveDecoder


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


def build_keyed_archive(root):
    objects = ["$null"]

    def encode(value):
        if value is None:
            objects.append({"$classname": "NSNull", "$classes": ["NSNull", "NSObject"]})
            return plistlib.UID(len(objects) - 1)
        if isinstance(value, dict):
            keys = []
            values = []
            for key, item in value.items():
                objects.append(str(key))
                keys.append(plistlib.UID(len(objects) - 1))
                values.append(encode(item))
            objects.append(
                {
                    "NS.keys": keys,
                    "NS.objects": values,
                    "$class": plistlib.UID(_dict_class_index()),
                }
            )
            return plistlib.UID(len(objects) - 1)
        if isinstance(value, list):
            objects.append(
                {
                    "NS.objects": [encode(item) for item in value],
                    "$class": plistlib.UID(_array_class_index()),
                }
            )
            return plistlib.UID(len(objects) - 1)

        objects.append(value)
        return plistlib.UID(len(objects) - 1)

    def _array_class_index():
        objects.append({"$classname": "NSArray", "$classes": ["NSArray", "NSObject"]})
        return len(objects) - 1

    def _dict_class_index():
        objects.append({"$classname": "NSDictionary", "$classes": ["NSDictionary", "NSObject"]})
        return len(objects) - 1

    root_uid = encode(root)
    return {
        "$version": 100000,
        "$archiver": "NSKeyedArchiver",
        "$top": {"root": root_uid},
        "$objects": objects,
    }


def write_manifest_cache(manifest_path, rows: list[tuple[str, dict]]):
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(manifest_path)
    conn.execute(
        """
        create table manifest (
            key TEXT primary key,
            filename TEXT,
            size INTEGER,
            inline_data BLOB,
            modification_time INTEGER,
            last_access_time INTEGER,
            extended_data BLOB
        )
        """
    )
    for index, (key, payload) in enumerate(rows, start=1):
        blob = plistlib.dumps(build_keyed_archive(payload), fmt=plistlib.FMT_BINARY)
        conn.execute(
            """
            insert into manifest(key, filename, size, inline_data, modification_time, last_access_time, extended_data)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (key, None, len(blob), blob, index, index, b""),
        )
    conn.commit()
    conn.close()


def test_keyed_archive_decoder_decodes_nested_dicts():
    payload = {"data": [{"stock_code": "603063", "stock_name": "禾望电气"}], "success": True}
    decoded = NSKeyedArchiveDecoder(build_keyed_archive(payload)).decode()
    assert decoded["data"][0]["stock_code"] == "603063"
    assert decoded["success"] is True


def test_macos_backend_fetches_today_trades_from_manifest_cache(tmp_path):
    container = tmp_path / "container"
    manifest_path = container / "Data/Library/Caches/kPPNetworkResponseCache/manifest.sqlite"
    app_path = tmp_path / "同花顺.app"
    app_path.mkdir()
    write_manifest_cache(
        manifest_path,
        [
            (
                'https://apigate.10jqka.com.cn/proxy/f10/arsenal/ipo/v1/astock/info{"module":"today_order"}',
                {
                    "status_msg": "ok",
                    "data": [
                        {
                            "证券代码": "603063",
                            "证券名称": "禾望电气",
                            "操作": "证券卖出",
                            "成交数量": "100",
                            "成交均价": "41.43",
                            "成交时间": "14:04:34",
                        }
                    ],
                    "status_code": 0,
                    "success": True,
                },
            )
        ],
    )
    connector = THSConnector(
        {
            "backend": THSConnector.BACKEND_MACOS_LOCAL,
            "trade_date": timezone.localdate(),
            "ths_mac_container_path": str(container),
            "ths_mac_app_path": str(app_path),
        }
    )

    trades = connector.fetch_today_trades()

    assert len(trades) == 1
    assert trades[0]["stock_code"] == "603063"
    assert trades[0]["direction"] == TradeRecord.Direction.SELL
    assert trades[0]["price"] == Decimal("41.43")


def test_macos_backend_fetches_positions_from_manifest_cache(tmp_path):
    container = tmp_path / "container"
    manifest_path = container / "Data/Library/Caches/kPPNetworkResponseCache/manifest.sqlite"
    app_path = tmp_path / "同花顺.app"
    app_path.mkdir()
    write_manifest_cache(
        manifest_path,
        [
            (
                "https://trade.10jqka.com.cn/query/position",
                {
                    "data": [
                        {
                            "证券代码": "603063",
                            "证券名称": "禾望电气",
                            "当前拥股数": "300",
                            "成本价": "39.201",
                            "交易市场": "上海Ａ股",
                        }
                    ]
                },
            )
        ],
    )
    connector = THSConnector(
        {
            "backend": THSConnector.BACKEND_MACOS_LOCAL,
            "ths_mac_container_path": str(container),
            "ths_mac_app_path": str(app_path),
        }
    )

    positions = connector.fetch_positions()

    assert len(positions) == 1
    assert positions[0]["stock_code"] == "603063"
    assert positions[0]["quantity"] == 300
    assert positions[0]["weighted_avg_cost"] == Decimal("39.201")


def test_macos_backend_fetches_today_trades_from_xcs_trade_file(tmp_path):
    container = tmp_path / "container"
    app_path = tmp_path / "同花顺.app"
    app_path.mkdir()
    xcs_path = container / "Data/Documents/XcsFold/XcsLscjDataFile_880002210930_744674551"
    xcs_path.parent.mkdir(parents=True, exist_ok=True)
    xcs_path.write_text(
        json.dumps(
            {
                "603063": {
                    "20260421": [
                        {
                            "cjsj": "14:04:34",
                            "zqdm": "603063",
                            "cjrq": "20260421",
                            "cjjg": "41.430",
                            "cjsl": "100.000",
                            "czmc": "卖出",
                            "zqmc": "禾望电气",
                        }
                    ],
                    "20260420": [
                        {
                            "cjsj": "13:06:59",
                            "zqdm": "603063",
                            "cjrq": "20260420",
                            "cjjg": "41.640",
                            "cjsl": "200.000",
                            "czmc": "买入",
                            "zqmc": "禾望电气",
                        }
                    ],
                },
                "startdate": "20250508",
                "enddate": "20260508",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    connector = THSConnector(
        {
            "backend": THSConnector.BACKEND_MACOS_LOCAL,
            "trade_date": datetime(2026, 4, 21).date(),
            "ths_mac_container_path": str(container),
            "ths_mac_app_path": str(app_path),
        }
    )

    trades = connector.fetch_today_trades()

    assert len(trades) == 1
    assert trades[0]["stock_code"] == "603063"
    assert trades[0]["direction"] == TradeRecord.Direction.SELL
    assert trades[0]["price"] == Decimal("41.430")


def test_macos_backend_reconstructs_positions_from_xcs_trade_file(tmp_path):
    container = tmp_path / "container"
    app_path = tmp_path / "同花顺.app"
    app_path.mkdir()
    xcs_path = container / "Data/Documents/XcsFold/XcsLscjDataFile_880002210930_744674551"
    xcs_path.parent.mkdir(parents=True, exist_ok=True)
    xcs_path.write_text(
        json.dumps(
            {
                "603063": {
                    "20260420": [
                        {
                            "cjsj": "13:06:59",
                            "zqdm": "603063",
                            "cjrq": "20260420",
                            "cjjg": "41.640",
                            "cjsl": "200.000",
                            "czmc": "买入",
                            "zqmc": "禾望电气",
                        }
                    ],
                    "20260421": [
                        {
                            "cjsj": "14:04:34",
                            "zqdm": "603063",
                            "cjrq": "20260421",
                            "cjjg": "41.430",
                            "cjsl": "100.000",
                            "czmc": "卖出",
                            "zqmc": "禾望电气",
                        }
                    ],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    connector = THSConnector(
        {
            "backend": THSConnector.BACKEND_MACOS_LOCAL,
            "ths_mac_container_path": str(container),
            "ths_mac_app_path": str(app_path),
        }
    )

    positions = connector.fetch_positions()

    assert len(positions) == 1
    assert positions[0]["stock_code"] == "603063"
    assert positions[0]["quantity"] == 100
    assert positions[0]["weighted_avg_cost"] == Decimal("41.640")


def test_normalize_trade_allows_missing_stock_name_for_macos_file_rows():
    connector = THSConnector({"backend": THSConnector.BACKEND_MACOS_LOCAL, "trade_date": timezone.localdate()})
    trade = connector._normalize_trade(
        {
            "stock_code": "002353",
            "stock_name": "",
            "business_price": "94.000",
            "business_amount": "100.000",
            "operation": "卖出",
            "business_time": "2026-02-03T09:34:03",
        }
    )

    assert trade["stock_name"] == "002353"


def test_macos_backend_connection_requires_app_running_when_configured(tmp_path):
    container = tmp_path / "container"
    manifest_path = container / "Data/Library/Caches/kPPNetworkResponseCache/manifest.sqlite"
    app_path = tmp_path / "同花顺.app"
    app_path.mkdir()
    write_manifest_cache(
        manifest_path,
        [("https://trade.10jqka.com.cn/query/position", {"data": []})],
    )

    connector = THSConnector(
        {
            "backend": THSConnector.BACKEND_MACOS_LOCAL,
            "ths_mac_container_path": str(container),
            "ths_mac_app_path": str(app_path),
            "ths_mac_require_app_running": True,
            "ths_mac_app_running_checker": lambda: False,
        }
    )

    assert connector.test_connection() is False


def test_macos_backend_inspect_cache_reports_candidate_payloads(tmp_path):
    container = tmp_path / "container"
    manifest_path = container / "Data/Library/Caches/kPPNetworkResponseCache/manifest.sqlite"
    app_path = tmp_path / "同花顺.app"
    app_path.mkdir()
    write_manifest_cache(
        manifest_path,
        [
            (
                'https://apigate.10jqka.com.cn/proxy/f10/arsenal/ipo/v1/astock/info{"module":"today_order"}',
                {
                    "status_msg": "ok",
                    "data": [
                        {
                            "证券代码": "603063",
                            "证券名称": "禾望电气",
                            "操作": "证券卖出",
                            "成交数量": "100",
                            "成交均价": "41.43",
                            "成交时间": "14:04:34",
                        }
                    ],
                    "status_code": 0,
                    "success": True,
                },
            )
        ],
    )
    connector = THSConnector(
        {
            "backend": THSConnector.BACKEND_MACOS_LOCAL,
            "trade_date": timezone.localdate(),
            "ths_mac_container_path": str(container),
            "ths_mac_app_path": str(app_path),
        }
    )

    report = connector.macos_backend.inspect_cache(limit=10)

    assert report["available"] is True
    assert report["recent_manifest_keys"]
    assert report["candidate_payloads"][0]["trade_rows"] == 1


def test_macos_backend_inspect_cache_related_only_filters_payloads(tmp_path):
    container = tmp_path / "container"
    manifest_path = container / "Data/Library/Caches/kPPNetworkResponseCache/manifest.sqlite"
    app_path = tmp_path / "同花顺.app"
    app_path.mkdir()
    write_manifest_cache(
        manifest_path,
        [
            ("https://push.10jqka.com.cn/interface/main.php?mod=msgCenter", {"list": []}),
            ("https://trade.10jqka.com.cn/query/position", {"data": []}),
        ],
    )
    connector = THSConnector(
        {
            "backend": THSConnector.BACKEND_MACOS_LOCAL,
            "ths_mac_container_path": str(container),
            "ths_mac_app_path": str(app_path),
        }
    )

    report = connector.macos_backend.inspect_cache(limit=10, related_only=True)

    assert len(report["candidate_payloads"]) == 1
    assert "position" in report["candidate_payloads"][0]["key"]
