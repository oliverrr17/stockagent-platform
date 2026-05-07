from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from portfolio.models import Position
from portfolio.services import HKStockStats
from trades.models import TradeRecord


class CostCalculator:
    def __init__(self, market_api=None):
        self.market_api = market_api

    @staticmethod
    def trade_fee_total(trade) -> Decimal:
        return (
            Decimal(str(getattr(trade, "commission", 0)))
            + Decimal(str(getattr(trade, "stamp_duty", 0)))
            + Decimal(str(getattr(trade, "other_fees", 0)))
        )

    @classmethod
    def weighted_avg_after_buy(cls, current_qty: int, current_weighted_avg_cost: Decimal, buy_trade) -> Decimal:
        current_cost_basis = Decimal(current_qty) * Decimal(str(current_weighted_avg_cost))
        trade_total_cost = Decimal(str(buy_trade.price)) * Decimal(buy_trade.quantity) + cls.trade_fee_total(buy_trade)
        new_qty = current_qty + int(buy_trade.quantity)
        if new_qty <= 0:
            return Decimal("0")
        return (current_cost_basis + trade_total_cost) / Decimal(new_qty)

    @classmethod
    def realized_pnl_for_sell(cls, weighted_avg_cost: Decimal, sell_trade) -> Decimal:
        gross_proceeds = Decimal(str(sell_trade.price)) * Decimal(sell_trade.quantity)
        return (gross_proceeds - cls.trade_fee_total(sell_trade)) - (
            Decimal(str(weighted_avg_cost)) * Decimal(sell_trade.quantity)
        )

    def calculate_weighted_avg_cost(self, stock_code: str):
        position = self._get_position(stock_code)
        return Decimal(str(position.weighted_avg_cost)) if position else Decimal("0")

    def calculate_realized_pnl(self, stock_code: str, sell_trade):
        position = self._get_position(stock_code)
        if position is None:
            raise ValueError(f"Position not found for stock_code={stock_code}")
        return self.realized_pnl_for_sell(position.weighted_avg_cost, sell_trade)

    def calculate_unrealized_pnl(self, stock_code: str):
        position = self._get_position(stock_code)
        if position is None or position.quantity <= 0:
            return Decimal("0")

        latest_price = self._get_latest_price(stock_code, position.market, fallback=position.weighted_avg_cost)
        return (latest_price - Decimal(str(position.weighted_avg_cost))) * Decimal(position.quantity)

    def get_hk_stock_stats(self, stock_code: str):
        position = self._get_position(stock_code, market=TradeRecord.Market.HK_STOCK)
        if position is None:
            raise ValueError(f"HK position not found for stock_code={stock_code}")

        latest_price = self._get_latest_price(stock_code, position.market, fallback=position.weighted_avg_cost)
        previous_close = self._get_previous_close(stock_code, position.market, fallback=latest_price)
        quantity = int(position.quantity)
        weighted_avg_cost = Decimal(str(position.weighted_avg_cost))
        market_value = latest_price * Decimal(quantity)
        unrealized_pnl = (latest_price - weighted_avg_cost) * Decimal(quantity)
        cost_basis = weighted_avg_cost * Decimal(quantity)
        unrealized_pnl_pct = (
            (unrealized_pnl / cost_basis) * Decimal("100") if cost_basis > 0 else Decimal("0")
        )
        daily_pnl = self._daily_pnl_for_stock_date(
            stock_code=stock_code,
            market=position.market,
            latest_price=latest_price,
            previous_close=previous_close,
            end_quantity=quantity,
        )

        stats = HKStockStats(
            stock_code=position.stock_code,
            stock_name=position.stock_name,
            weighted_avg_cost=weighted_avg_cost,
            quantity=quantity,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            realized_pnl=Decimal(str(position.realized_pnl)),
            daily_pnl=daily_pnl,
        )
        return asdict(stats)

    def get_trade_history(self, stock_code: str):
        return TradeRecord.objects.filter(stock_code=stock_code, market=TradeRecord.Market.HK_STOCK).order_by(
            "trade_time"
        )

    def _get_position(self, stock_code: str, market: str | None = None):
        queryset = Position.objects.filter(stock_code=stock_code)
        if market:
            queryset = queryset.filter(market=market)
        return queryset.order_by("-updated_at").first()

    def _get_latest_price(self, stock_code: str, market: str, fallback: Decimal) -> Decimal:
        if self.market_api is None:
            return Decimal(str(fallback))

        if callable(self.market_api):
            value = self.market_api(stock_code, market)
            return Decimal(str(value))

        for method_name in ("get_latest_price", "get_price", "latest_price"):
            method = getattr(self.market_api, method_name, None)
            if callable(method):
                value = method(stock_code, market)
                return Decimal(str(value))

        snapshot = self._get_snapshot(stock_code, market)
        for key in ("latest_price", "price", "last_price", "close"):
            if key in snapshot and snapshot[key] is not None:
                return Decimal(str(snapshot[key]))

        return Decimal(str(fallback))

    def _get_previous_close(self, stock_code: str, market: str, fallback: Decimal) -> Decimal:
        if self.market_api is None:
            return Decimal(str(fallback))

        for method_name in ("get_previous_close", "previous_close", "prev_close"):
            method = getattr(self.market_api, method_name, None)
            if callable(method):
                value = method(stock_code, market)
                return Decimal(str(value))

        snapshot = self._get_snapshot(stock_code, market)
        for key in ("previous_close", "prev_close", "yesterday_close"):
            if key in snapshot and snapshot[key] is not None:
                return Decimal(str(snapshot[key]))

        return Decimal(str(fallback))

    def _get_snapshot(self, stock_code: str, market: str) -> dict:
        if self.market_api is None:
            return {}

        for method_name in ("get_snapshot", "snapshot", "quote"):
            method = getattr(self.market_api, method_name, None)
            if callable(method):
                try:
                    result = method(stock_code, market)
                except Exception:
                    return {}
                if isinstance(result, dict):
                    return result
        return {}

    def _daily_pnl_for_stock_date(
        self,
        *,
        stock_code: str,
        market: str,
        latest_price: Decimal,
        previous_close: Decimal,
        end_quantity: int,
    ) -> Decimal:
        snapshot = self._get_snapshot(stock_code, market)
        trade_date = self._snapshot_trade_date(snapshot)
        if trade_date is None:
            return (latest_price - previous_close) * Decimal(end_quantity)

        trades = list(
            TradeRecord.objects.filter(
                stock_code=stock_code,
                market=market,
                trade_time__date=trade_date,
            ).order_by("trade_time", "id")
        )
        if not trades:
            return (latest_price - previous_close) * Decimal(end_quantity)

        start_quantity = end_quantity
        trade_cash_delta = Decimal("0")
        for trade in trades:
            gross_amount = Decimal(str(trade.price)) * Decimal(trade.quantity)
            fees = self.trade_fee_total(trade)
            if trade.direction == TradeRecord.Direction.BUY:
                start_quantity -= int(trade.quantity)
                trade_cash_delta -= gross_amount + fees
            else:
                start_quantity += int(trade.quantity)
                trade_cash_delta += gross_amount - fees

        start_value = previous_close * Decimal(start_quantity)
        end_value = latest_price * Decimal(end_quantity)
        return end_value + trade_cash_delta - start_value

    def _snapshot_trade_date(self, snapshot: dict) -> date | None:
        raw_value = snapshot.get("trade_date")
        if not raw_value:
            return None
        if isinstance(raw_value, date) and not isinstance(raw_value, datetime):
            return raw_value
        text = str(raw_value).strip()
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return date.fromisoformat(text)
