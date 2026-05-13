from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
import logging

from django.utils import timezone

from trades.models import TradeRecord


logger = logging.getLogger(__name__)


class FutuConnector:
    FEE_BATCH_SIZE = 400

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.acc_id = int(self.config.get("acc_id", 0) or 0)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 11111) or 11111)
        self.security_firm = str(self.config.get("security_firm", "")).strip().upper()
        self.trade_context_factory = self.config.get("trade_context_factory")
        self.trade_context = None

    def fetch_trade_records(self, start: date | None = None, end: date | None = None) -> list[dict]:
        context = self._get_trade_context()
        account = self._resolve_account(context)
        orders = self._fetch_orders(context, account, start=start, end=end)
        fee_map = self._fetch_fee_map(context, account, orders)
        return [self._normalize_order(order, fee_map.get(str(order["order_id"]), {})) for order in orders]

    def _get_trade_context(self):
        if self.trade_context is not None:
            return self.trade_context
        if callable(self.trade_context_factory):
            self.trade_context = self.trade_context_factory(host=self.host, port=self.port)
            return self.trade_context

        from futu import OpenSecTradeContext  # type: ignore

        self.trade_context = OpenSecTradeContext(host=self.host, port=self.port)
        return self.trade_context

    def _resolve_account(self, context):
        ret, rows = context.get_acc_list()
        if ret != 0:
            raise RuntimeError("Failed to query Futu accounts.")

        for row in list(rows or []):
            if int(row.get("acc_id", 0) or 0) != self.acc_id:
                continue
            if str(row.get("trd_env", "")).upper() != "REAL":
                raise ValueError("Configured Futu account is not a Hong Kong real account.")
            if "HK" not in str(row.get("trdmarket_auth", "")).upper():
                raise ValueError("Configured Futu account lacks Hong Kong market authorization.")
            if self.security_firm and str(row.get("security_firm", "")).strip().upper() != self.security_firm:
                raise ValueError("Configured Futu account security firm does not match.")
            return row

        raise ValueError("Configured Futu Hong Kong real account was not found.")

    def _fetch_orders(self, context, account: dict, start: date | None = None, end: date | None = None) -> list[dict]:
        ret, rows = context.history_order_list_query(
            acc_id=int(account["acc_id"]),
            start=start,
            end=end,
        )
        if ret != 0:
            raise RuntimeError("Failed to query Futu historical orders.")

        orders = []
        for row in list(rows or []):
            if int(row.get("dealt_qty", 0) or 0) <= 0:
                continue
            orders.append(row)
        return orders

    def _fetch_fee_map(self, context, account: dict, orders: list[dict]) -> dict[str, dict]:
        if not orders:
            return {}

        fee_map: dict[str, dict] = {}
        order_ids = [str(item["order_id"]).strip() for item in orders]
        for index in range(0, len(order_ids), self.FEE_BATCH_SIZE):
            batch_ids = order_ids[index : index + self.FEE_BATCH_SIZE]
            ret, rows = context.order_fee_query(
                order_id_list=batch_ids,
                acc_id=int(account["acc_id"]),
            )
            if ret != 0:
                raise RuntimeError("Failed to query Futu order fees.")
            for row in list(rows or []):
                fee_map[str(row.get("order_id", "")).strip()] = row
        return fee_map

    def _normalize_order(self, order: dict, fee_row: dict) -> dict:
        fee_details = list(fee_row.get("fee_details") or [])
        commission = Decimal("0")
        stamp_duty = Decimal("0")
        other_fees = Decimal("0")

        for item in fee_details:
            fee_name = str(item.get("fee_name", "")).strip().lower()
            amount = Decimal(str(item.get("fee_amount", 0)))
            if fee_name == "commission":
                commission += amount
            elif fee_name == "stamp duty":
                stamp_duty += amount
            else:
                other_fees += amount

        stock_code = str(order.get("code", "")).split(".")[-1].zfill(5)
        updated_time = timezone.make_aware(
            datetime.strptime(str(order["updated_time"]), "%Y-%m-%d %H:%M:%S"),
            timezone.get_current_timezone(),
        )

        return {
            "stock_code": stock_code,
            "stock_name": str(order.get("stock_name") or order.get("code_name") or stock_code).strip(),
            "market": TradeRecord.Market.HK_STOCK,
            "direction": self._normalize_direction(order.get("trd_side", "")),
            "price": Decimal(str(order.get("dealt_avg_price", 0))),
            "quantity": int(order.get("dealt_qty", 0)),
            "trade_time": updated_time,
            "source": TradeRecord.Source.FUTU_API,
            "external_trade_id": str(order.get("order_id", "")).strip(),
            "commission": commission,
            "stamp_duty": stamp_duty,
            "other_fees": other_fees,
            "fee_details": fee_details,
        }

    def _normalize_direction(self, value: str) -> str:
        text = str(value).strip().upper()
        if text in {"BUY", "TRD_SIDE_BUY"}:
            return TradeRecord.Direction.BUY
        if text in {"SELL", "TRD_SIDE_SELL"}:
            return TradeRecord.Direction.SELL
        raise ValueError(f"Unsupported Futu trade direction: {value}")
