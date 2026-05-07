from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from portfolio.models import Position
from portfolio.services.cost_calculator import CostCalculator
from trades.models import TradeRecord


class ReviewEvidenceBuilder:
    def __init__(self, market_api=None):
        self.market_api = market_api

    def build(
        self,
        trade,
        *,
        volume_analysis: dict,
        chip_analysis: dict,
        trend_analysis: dict,
        market_heat: dict,
        industry_heat: dict,
        company_quality: dict,
    ):
        intent_snapshot = self._serialize_intent_snapshot(trade)
        position = Position.objects.filter(stock_code=trade.stock_code, market=trade.market).order_by("-updated_at").first()
        pnl_context = self._build_pnl_context(trade, position)
        forward_path = self._build_forward_path(trade)

        return {
            "trade": {
                "id": trade.id,
                "stock_code": trade.stock_code,
                "stock_name": trade.stock_name,
                "market": trade.market,
                "direction": trade.direction,
                "price": float(Decimal(str(trade.price))),
                "quantity": int(trade.quantity),
                "trade_time": trade.trade_time.isoformat(),
                "source": trade.source,
                "fees_total": float(
                    Decimal(str(trade.commission))
                    + Decimal(str(trade.stamp_duty))
                    + Decimal(str(trade.other_fees))
                ),
            },
            "intent_snapshot": intent_snapshot,
            "position_context": {
                "status": getattr(position, "status", ""),
                "quantity": getattr(position, "quantity", 0),
                "weighted_avg_cost": str(getattr(position, "weighted_avg_cost", "")) if position else "",
                "realized_pnl": str(getattr(position, "realized_pnl", "")) if position else "",
            },
            "pnl_context": pnl_context,
            "forward_path": forward_path,
            "market_heat": market_heat,
            "industry_heat": industry_heat,
            "company_quality": company_quality,
            "volume_analysis": volume_analysis,
            "chip_analysis": chip_analysis,
            "trend_analysis": trend_analysis,
        }

    def _serialize_intent_snapshot(self, trade):
        snapshot = trade.__dict__.get("intent_snapshot")
        if snapshot is None:
            try:
                snapshot = trade.intent_snapshot
            except Exception:
                snapshot = None
        if snapshot is None:
            return {
                "setup_tags": [],
                "market_context_tags": [],
                "security_quality_tags": [],
                "execution_emotion_tags": [],
                "overall_notes": "",
                "planned_holding_period": "",
                "planned_stop_loss_type": "",
                "planned_stop_loss_value": None,
                "planned_take_profit_type": "",
                "planned_take_profit_value": None,
                "degraded": True,
                "degraded_reason": "trade_intent_snapshot_missing",
            }
        return {
            "setup_tags": list(getattr(snapshot, "setup_tags", []) or []),
            "market_context_tags": list(getattr(snapshot, "market_context_tags", []) or []),
            "security_quality_tags": list(getattr(snapshot, "security_quality_tags", []) or []),
            "execution_emotion_tags": list(getattr(snapshot, "execution_emotion_tags", []) or []),
            "overall_notes": str(getattr(snapshot, "overall_notes", "") or ""),
            "planned_holding_period": str(getattr(snapshot, "planned_holding_period", "") or ""),
            "planned_stop_loss_type": str(getattr(snapshot, "planned_stop_loss_type", "") or ""),
            "planned_stop_loss_value": self._maybe_float(getattr(snapshot, "planned_stop_loss_value", None)),
            "planned_take_profit_type": str(getattr(snapshot, "planned_take_profit_type", "") or ""),
            "planned_take_profit_value": self._maybe_float(getattr(snapshot, "planned_take_profit_value", None)),
            "degraded": False,
            "degraded_reason": "",
        }

    def _build_pnl_context(self, trade, position):
        realized_trade_pnl = None
        if trade.direction == TradeRecord.Direction.SELL and position is not None:
            realized_trade_pnl = CostCalculator.realized_pnl_for_sell(
                Decimal(str(position.weighted_avg_cost)),
                trade,
            )
        return {
            "realized_trade_pnl": self._maybe_float(realized_trade_pnl),
            "has_open_position_after_trade": bool(position and position.quantity > 0),
        }

    def _build_forward_path(self, trade):
        if self.market_api is None:
            return {
                "max_favorable_excursion_pct": None,
                "max_adverse_excursion_pct": None,
                "post_trade_5d_return_pct": None,
                "degraded": True,
                "degraded_reason": "market_api_unavailable",
            }

        start = trade.trade_time.date()
        end = start + timedelta(days=10)
        try:
            bars = self.market_api.fetch_daily_bars(trade.stock_code, start=start, end=end, market=trade.market)
        except Exception:
            bars = []
        if not bars:
            return {
                "max_favorable_excursion_pct": None,
                "max_adverse_excursion_pct": None,
                "post_trade_5d_return_pct": None,
                "degraded": True,
                "degraded_reason": "forward_bars_unavailable",
            }

        entry = Decimal(str(trade.price))
        highs = [Decimal(str(item["high"])) for item in bars if item.get("high") is not None]
        lows = [Decimal(str(item["low"])) for item in bars if item.get("low") is not None]
        closes = [Decimal(str(item["close"])) for item in bars if item.get("close") is not None]
        max_high = max(highs) if highs else entry
        min_low = min(lows) if lows else entry
        exit_close = closes[min(4, len(closes) - 1)] if closes else entry

        if trade.direction == TradeRecord.Direction.BUY:
            mfe = ((max_high - entry) / entry * Decimal("100")).quantize(Decimal("0.0001"))
            mae = ((min_low - entry) / entry * Decimal("100")).quantize(Decimal("0.0001"))
            post_return = ((exit_close - entry) / entry * Decimal("100")).quantize(Decimal("0.0001"))
        else:
            mfe = ((entry - min_low) / entry * Decimal("100")).quantize(Decimal("0.0001"))
            mae = ((entry - max_high) / entry * Decimal("100")).quantize(Decimal("0.0001"))
            post_return = ((entry - exit_close) / entry * Decimal("100")).quantize(Decimal("0.0001"))

        return {
            "max_favorable_excursion_pct": float(mfe),
            "max_adverse_excursion_pct": float(mae),
            "post_trade_5d_return_pct": float(post_return),
            "degraded": False,
            "degraded_reason": "",
        }

    def _maybe_float(self, value):
        if value in (None, ""):
            return None
        return float(Decimal(str(value)))
