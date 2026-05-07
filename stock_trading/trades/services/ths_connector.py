from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import logging
from pathlib import Path
import tempfile
import subprocess
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from trades.models import TradeRecord


logger = logging.getLogger(__name__)

STOCK_CODE_CN = "\u8bc1\u5238\u4ee3\u7801"
STOCK_NAME_CN = "\u8bc1\u5238\u540d\u79f0"
DIRECTION_CN = "\u4e70\u5356\u6807\u5fd7"
DIRECTION_ALT_CN = "\u64cd\u4f5c"
PRICE_CN = "\u6210\u4ea4\u4ef7\u683c"
PRICE_AVG_CN = "\u6210\u4ea4\u5747\u4ef7"
QUANTITY_CN = "\u6210\u4ea4\u6570\u91cf"
TRADE_TIME_CN = "\u6210\u4ea4\u65f6\u95f4"
POSITION_QTY_CN = "\u5f53\u524d\u6570\u91cf"
POSITION_COST_CN = "\u644a\u8584\u6210\u672c\u4ef7"
POSITION_QTY_ALT_CN = "\u5f53\u524d\u62e5\u80a1\u6570"
POSITION_COST_ALT_CN = "\u6210\u672c\u4ef7"
POSITION_MARKET_CN = "\u4ea4\u6613\u5e02\u573a"

try:
    import easytrader  # type: ignore
except ImportError:  # pragma: no cover - optional dependency for runtime only
    easytrader = None


class THSConnector:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.exe_path = self.config.get("exe_path")
        self.client_type = self.config.get("client_type", "ths")
        self.client_factory = self.config.get("client_factory")
        self.user = self.config.get("user")
        self.trade_date = self.config.get("trade_date") or timezone.localdate()

        self.bridge_python = self.config.get("bridge_python")
        self.bridge_script = Path(
            self.config.get("bridge_script") or Path(__file__).with_name("ths_bridge_client.py")
        )
        self.window_title_keyword = self.config.get(
            "window_title_keyword", "\u80a1\u7968\u4ea4\u6613\u7cfb\u7edf"
        )
        self.bridge_runner = self.config.get("bridge_runner")

    def connect(self) -> bool:
        tester = self.config.get("tester")
        if callable(tester):
            return bool(tester())

        if self.bridge_python:
            try:
                probe_result = self._invoke_bridge("probe")
                return bool(probe_result.get("ok"))
            except Exception as exc:
                logger.error("THS bridge probe failed: %s", exc)
                return False

        try:
            if self.user is None:
                self.user = self._build_user()
            elif not self.exe_path:
                return True

            connect_callable = getattr(self.user, "connect", None)
            if callable(connect_callable):
                if not self.exe_path:
                    raise ValueError("THS exe_path is required for direct client connections.")
                connect_callable(self.exe_path)

            return True
        except Exception as exc:
            logger.error("THS connector connection failed: %s", exc)
            return False

    def fetch_today_trades(self) -> list[dict]:
        raw_trades = self._read_today_trades()
        normalized: list[dict] = []
        for trade in raw_trades:
            try:
                normalized.append(self._normalize_trade(trade))
            except Exception as exc:
                logger.warning("Skipping THS trade row due to parse error: %s", exc)
        return normalized

    def fetch_trade_records(self, start_date: date, end_date: date) -> list[dict]:
        fetcher = self.config.get("fetcher")
        if callable(fetcher):
            return fetcher(start_date, end_date)

        records = self.config.get("records")
        if records is not None:
            filtered_records = []
            for record in records:
                trade_date = self._extract_trade_date(record)
                if trade_date is not None and start_date <= trade_date <= end_date:
                    filtered_records.append(record)
            return filtered_records

        today = timezone.localdate()
        if start_date <= today <= end_date:
            return self.fetch_today_trades()
        return []

    def fetch_positions(self) -> list[dict]:
        if self.bridge_python:
            result = self._invoke_bridge("positions")
            return [self._normalize_position(item) for item in list(result or [])]
        if not self.connect():
            return []
        raw_positions = self._read_positions()
        return [self._normalize_position(item) for item in raw_positions]

    def fetch_balance(self) -> list[dict]:
        if self.bridge_python:
            return []
        if not self.connect():
            return []
        return list(getattr(self.user, "balance", []) or [])

    def test_connection(self) -> bool:
        return self.connect()

    def _build_user(self):
        if callable(self.client_factory):
            return self.client_factory()
        if easytrader is None:
            raise RuntimeError("easytrader is not installed.")
        return easytrader.use(self.client_type)

    def _read_today_trades(self) -> list[dict]:
        if self.bridge_python:
            result = self._invoke_bridge("today_trades")
            return list(result or [])

        if not self.connect():
            return []

        trades = getattr(self.user, "today_trades", [])
        return list(trades or [])

    def _read_positions(self) -> list[dict]:
        positions = list(getattr(self.user, "position", []) or [])
        if positions:
            return positions

        try:
            from easytrader.grid_strategies import Xls  # type: ignore
        except ImportError:
            return []

        strategy = Xls(tmp_folder=tempfile.gettempdir())
        strategy.set_trader(self.user)
        try:
            return strategy.get(self.user.config.COMMON_GRID_CONTROL_ID) or []
        except Exception as exc:
            logger.warning("THS XLS fallback for positions failed: %s", exc)
            return []

    def _invoke_bridge(self, mode: str) -> Any:
        if callable(self.bridge_runner):
            return self.bridge_runner(mode=mode, window_title_keyword=self.window_title_keyword)

        if not self.bridge_python:
            raise RuntimeError("THS bridge_python is not configured.")
        if not Path(self.bridge_python).exists():
            raise FileNotFoundError(f"THS bridge python not found: {self.bridge_python}")
        if not self.bridge_script.exists():
            raise FileNotFoundError(f"THS bridge script not found: {self.bridge_script}")

        result = subprocess.run(
            [
                self.bridge_python,
                str(self.bridge_script),
                "--mode",
                mode,
                "--window-title-keyword",
                self.window_title_keyword,
            ],
            capture_output=True,
            check=False,
        )
        stdout = self._decode_bridge_stream(result.stdout)
        stderr = self._decode_bridge_stream(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"THS bridge command failed: {stderr or stdout}")

        stdout = stdout.strip()
        if not stdout:
            return [] if mode == "today_trades" else {"ok": False}
        return json.loads(stdout)

    def _decode_bridge_stream(self, payload: bytes | str | None):
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload.strip()

        for encoding in ("utf-8", "gbk", "cp936"):
            try:
                return payload.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="replace").strip()

    def _normalize_trade(self, trade: dict) -> dict:
        stock_code = self._pick(trade, "stock_code", STOCK_CODE_CN)
        stock_name = self._pick(trade, "stock_name", STOCK_NAME_CN)
        direction_raw = self._pick(
            trade,
            "entrust_bs",
            DIRECTION_CN,
            "\u4e70\u5356\u65b9\u5411",
            DIRECTION_ALT_CN,
            "operation",
        )
        price_raw = self._pick(
            trade,
            "business_price",
            "business_avg_price",
            PRICE_CN,
            PRICE_AVG_CN,
            "price",
        )
        quantity_raw = self._pick(trade, "business_amount", QUANTITY_CN, "\u6210\u4ea4\u6570", "amount")
        trade_time_raw = self._pick(trade, "business_time", TRADE_TIME_CN, "trade_time")

        quantity_value = Decimal(str(quantity_raw).replace(",", ""))
        return {
            "stock_code": str(stock_code).strip().upper(),
            "stock_name": str(stock_name).strip(),
            "market": TradeRecord.Market.A_STOCK,
            "direction": self._normalize_direction(direction_raw),
            "price": Decimal(str(price_raw).replace(",", "")),
            "quantity": int(quantity_value),
            "trade_time": self._normalize_trade_time(trade_time_raw),
            "source": TradeRecord.Source.THS,
            "commission": Decimal("0"),
            "stamp_duty": Decimal("0"),
            "other_fees": Decimal("0"),
        }

    def _normalize_position(self, position: dict) -> dict:
        stock_code = self._pick(position, "stock_code", STOCK_CODE_CN)
        stock_name = self._pick(position, "stock_name", STOCK_NAME_CN)
        quantity_raw = self._pick(
            position,
            "current_amount",
            POSITION_QTY_CN,
            POSITION_QTY_ALT_CN,
            "quantity",
        )
        cost_raw = self._pick(
            position,
            "cost_price",
            POSITION_COST_CN,
            POSITION_COST_ALT_CN,
            "weighted_avg_cost",
            "price",
        )
        market_raw = position.get(POSITION_MARKET_CN) or position.get("market") or TradeRecord.Market.A_STOCK

        quantity = int(Decimal(str(quantity_raw).replace(",", "")))
        weighted_avg_cost = Decimal(str(cost_raw).replace(",", ""))
        return {
            "stock_code": str(stock_code).strip().upper(),
            "stock_name": str(stock_name).strip(),
            "market": self._normalize_position_market(market_raw),
            "quantity": quantity,
            "cost_price": weighted_avg_cost,
            "weighted_avg_cost": weighted_avg_cost,
            "total_invested": weighted_avg_cost * Decimal(quantity),
            "realized_pnl": Decimal("0"),
            "status": "ACTIVE" if quantity > 0 else "CLEARED",
        }

    def _pick(self, trade: dict, *keys):
        for key in keys:
            value = trade.get(key)
            if value not in (None, ""):
                return value
        raise ValueError(f"Missing expected THS field from trade row. Keys tried: {keys}")

    def _normalize_direction(self, value) -> str:
        text = str(value).strip().lower()
        if "\u4e70" in text or "buy" in text:
            return TradeRecord.Direction.BUY
        if "\u5356" in text or "\u6cbd" in text or "sell" in text:
            return TradeRecord.Direction.SELL
        raise ValueError(f"Unsupported THS direction value: {value}")

    def _normalize_trade_time(self, value):
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            parsed = parse_datetime(text)
            if parsed is None:
                if len(text) <= 8 and ":" in text:
                    parsed = datetime.fromisoformat(f"{self.trade_date.isoformat()}T{text}")
                else:
                    parsed = datetime.fromisoformat(text.replace("/", "-"))

        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def _normalize_position_market(self, value):
        text = str(value).strip()
        if "深" in text:
            return TradeRecord.Market.A_STOCK
        if "上" in text:
            return TradeRecord.Market.A_STOCK
        if text == TradeRecord.Market.A_STOCK:
            return TradeRecord.Market.A_STOCK
        if text == TradeRecord.Market.HK_STOCK:
            return TradeRecord.Market.HK_STOCK
        return TradeRecord.Market.A_STOCK

    def _extract_trade_date(self, record: dict):
        trade_time = record.get("trade_time")
        if trade_time is None:
            return None
        if isinstance(trade_time, datetime):
            return trade_time.date()

        text = str(trade_time).strip()
        parsed = parse_datetime(text)
        if parsed is not None:
            return parsed.date()
        if len(text) <= 8 and ":" in text:
            return self.trade_date
        return datetime.fromisoformat(text.replace("/", "-")).date()
