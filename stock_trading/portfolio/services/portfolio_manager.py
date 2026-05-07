from __future__ import annotations

from decimal import Decimal
import re

from django.db import transaction
from django.utils import timezone

from portfolio.models import Position, PositionEntry
from portfolio.services.cost_calculator import CostCalculator
from trades.models import TradeRecord


class PortfolioManager:
    def add_position(self, entry_data: dict):
        normalized = self._normalize_entry_data(entry_data)
        self._validate_stock_code(normalized["stock_code"], normalized["market"])

        with transaction.atomic():
            PositionEntry.objects.create(**normalized)
            position = self._get_or_create_position(normalized)
            if position.quantity > 0:
                total_cost = Decimal(str(position.weighted_avg_cost)) * Decimal(position.quantity)
                new_cost = Decimal(str(normalized["cost_price"])) * Decimal(normalized["quantity"])
                new_quantity = position.quantity + normalized["quantity"]
                weighted_avg_cost = (total_cost + new_cost) / Decimal(new_quantity)
            else:
                new_quantity = normalized["quantity"]
                weighted_avg_cost = Decimal(str(normalized["cost_price"]))

            position.stock_name = normalized["stock_name"]
            position.market = normalized["market"]
            position.quantity = new_quantity
            position.weighted_avg_cost = weighted_avg_cost
            position.cost_price = weighted_avg_cost
            position.total_invested = weighted_avg_cost * Decimal(new_quantity)
            position.status = Position.Status.ACTIVE if new_quantity > 0 else Position.Status.CLEARED
            position.save()
        return position

    def update_position(self, position_id: int, entry_data: dict):
        position = Position.objects.get(pk=position_id)
        normalized = self._normalize_entry_data(entry_data, allow_missing_entry_time=True)
        self._validate_stock_code(normalized["stock_code"], normalized["market"])

        with transaction.atomic():
            position.stock_code = normalized["stock_code"]
            position.stock_name = normalized["stock_name"]
            position.market = normalized["market"]
            position.quantity = normalized["quantity"]
            position.weighted_avg_cost = Decimal(str(normalized["cost_price"]))
            position.cost_price = Decimal(str(normalized["cost_price"]))
            position.total_invested = position.weighted_avg_cost * Decimal(position.quantity)
            position.status = Position.Status.ACTIVE if position.quantity > 0 else Position.Status.CLEARED
            position.save()
        return position

    def apply_trade(self, trade):
        position = self._get_or_create_position(
            {
                "stock_code": trade.stock_code,
                "stock_name": trade.stock_name,
                "market": trade.market,
            }
        )

        if trade.direction == TradeRecord.Direction.BUY:
            return self._apply_buy(position, trade)
        if trade.direction == TradeRecord.Direction.SELL:
            return self._apply_sell(position, trade)
        raise ValueError(f"Unsupported trade direction: {trade.direction}")

    @staticmethod
    def get_portfolio(market=None):
        queryset = Position.objects.all()
        if market:
            queryset = queryset.filter(market=market)
        return queryset

    @staticmethod
    def get_active_stock_codes():
        return list(
            Position.objects.filter(status=Position.Status.ACTIVE, quantity__gt=0)
            .values_list("stock_code", flat=True)
            .distinct()
        )

    def sync_position_snapshots(self, positions: list[dict], market: str) -> list[Position]:
        synced_positions: list[Position] = []
        seen_codes = set()

        with transaction.atomic():
            for item in positions:
                stock_code = str(item["stock_code"]).strip().upper()
                self._validate_stock_code(stock_code, market)
                seen_codes.add(stock_code)

                position = self._get_or_create_position(
                    {
                        "stock_code": stock_code,
                        "stock_name": item["stock_name"],
                        "market": market,
                    }
                )
                position.stock_name = str(item["stock_name"]).strip()
                position.market = market
                position.quantity = int(item["quantity"])
                position.cost_price = Decimal(str(item["cost_price"]))
                position.weighted_avg_cost = Decimal(str(item["weighted_avg_cost"]))
                position.total_invested = Decimal(str(item["total_invested"]))
                if "realized_pnl" in item:
                    position.realized_pnl = Decimal(str(item["realized_pnl"]))
                position.status = (
                    Position.Status.ACTIVE if position.quantity > 0 else Position.Status.CLEARED
                )
                position.save()
                synced_positions.append(position)

            stale_positions = Position.objects.filter(market=market).exclude(stock_code__in=seen_codes)
            for position in stale_positions:
                position.quantity = 0
                position.total_invested = Decimal("0")
                position.status = Position.Status.CLEARED
                position.save()

        return synced_positions

    def _apply_buy(self, position: Position, trade):
        with transaction.atomic():
            weighted_avg_cost = CostCalculator.weighted_avg_after_buy(
                position.quantity,
                Decimal(str(position.weighted_avg_cost or 0)),
                trade,
            )
            position.stock_name = trade.stock_name
            position.market = trade.market
            position.quantity += int(trade.quantity)
            position.weighted_avg_cost = weighted_avg_cost
            position.cost_price = weighted_avg_cost
            position.total_invested = weighted_avg_cost * Decimal(position.quantity)
            position.status = Position.Status.ACTIVE
            position.save()
        return position

    def _apply_sell(self, position: Position, trade):
        if position.quantity < int(trade.quantity):
            raise ValueError(
                f"Insufficient position quantity for stock_code={trade.stock_code}: "
                f"have {position.quantity}, need {trade.quantity}"
            )

        with transaction.atomic():
            realized_pnl = CostCalculator.realized_pnl_for_sell(
                Decimal(str(position.weighted_avg_cost)),
                trade,
            )
            position.stock_name = trade.stock_name
            position.market = trade.market
            position.quantity -= int(trade.quantity)
            position.realized_pnl = Decimal(str(position.realized_pnl)) + realized_pnl
            position.total_invested = Decimal(str(position.weighted_avg_cost)) * Decimal(position.quantity)
            position.status = Position.Status.ACTIVE if position.quantity > 0 else Position.Status.CLEARED
            position.save()
        return position

    def _get_or_create_position(self, data: dict):
        position = (
            Position.objects.filter(stock_code=data["stock_code"], market=data["market"])
            .order_by("-updated_at")
            .first()
        )
        if position:
            return position

        return Position.objects.create(
            stock_code=data["stock_code"],
            stock_name=data.get("stock_name", ""),
            market=data["market"],
            quantity=0,
            cost_price=Decimal("0"),
            weighted_avg_cost=Decimal("0"),
            total_invested=Decimal("0"),
            realized_pnl=Decimal("0"),
            status=Position.Status.CLEARED,
        )

    def _normalize_entry_data(self, entry_data: dict, allow_missing_entry_time: bool = False):
        normalized = dict(entry_data)
        normalized["stock_code"] = str(normalized["stock_code"]).strip().upper()
        normalized["stock_name"] = str(normalized["stock_name"]).strip()
        normalized["market"] = normalized["market"]
        normalized["quantity"] = int(normalized["quantity"])
        normalized["cost_price"] = Decimal(str(normalized["cost_price"]))
        if not allow_missing_entry_time:
            normalized["entry_time"] = normalized.get("entry_time") or timezone.now()
        return normalized

    def _validate_stock_code(self, stock_code: str, market: str):
        if market == TradeRecord.Market.A_STOCK and not re.fullmatch(r"\d{6}", stock_code):
            raise ValueError(f"Invalid A-stock code: {stock_code}")
        if market == TradeRecord.Market.HK_STOCK and not re.fullmatch(r"\d{5}", stock_code):
            raise ValueError(f"Invalid HK-stock code: {stock_code}")
