from __future__ import annotations

from decimal import Decimal

from analysis.services.market_data import SPECIAL_HK_ETF_CODES, trade_date_window
from trades.models import TradeRecord


class VolumeAnalyzer:
    def __init__(self, market_api=None):
        self.market_api = market_api

    def analyze(self, trade):
        if self.market_api and trade.market == TradeRecord.Market.A_STOCK:
            return self._analyze_with_daily_bars(trade)
        if self.market_api and trade.market == TradeRecord.Market.HK_STOCK and not self._is_special_hk_etf(trade.stock_code):
            return self._analyze_with_daily_bars(trade)
        return self._fallback_analysis(trade)

    def calculate_volume_ratios(self, volumes, trade_day_idx):
        raise NotImplementedError("Detailed market volume-ratio calculation is not implemented yet.")

    def detect_volume_pattern(self, volumes, prices):
        raise NotImplementedError("Detailed volume pattern detection is not implemented yet.")

    def _analyze_with_daily_bars(self, trade):
        lookback_days = 120 if trade.market == TradeRecord.Market.A_STOCK else 180
        start, end = trade_date_window(trade.trade_time, lookback_days=lookback_days)
        bars = self.market_api.fetch_daily_bars(trade.stock_code, start=start, end=end, market=trade.market)
        if not bars:
            return self._fallback_analysis(trade, degraded_reason=self._missing_bars_reason(trade))

        target_bar = bars[-1]
        previous_bars = bars[:-1] or bars
        target_volume = Decimal(str(target_bar["volume"]))
        amount = Decimal(str(target_bar["amount"]))

        avg5 = self._average([Decimal(str(item["volume"])) for item in previous_bars[-5:]])
        avg10 = self._average([Decimal(str(item["volume"])) for item in previous_bars[-10:]])
        avg20 = self._average([Decimal(str(item["volume"])) for item in previous_bars[-20:]])

        ratio5 = self._safe_ratio(target_volume, avg5)
        ratio10 = self._safe_ratio(target_volume, avg10)
        ratio20 = self._safe_ratio(target_volume, avg20)

        if ratio20 >= Decimal("1.50"):
            volume_signal = "high"
        elif ratio20 <= Decimal("0.70"):
            volume_signal = "low"
        else:
            volume_signal = "normal"

        close = Decimal(str(target_bar["close"]))
        pre_close = Decimal(str(target_bar["pre_close"]))
        if close > pre_close and ratio20 >= Decimal("1.80"):
            volume_pattern = "放量突破"
        elif close > pre_close and ratio20 >= Decimal("1.20"):
            volume_pattern = "放量上涨"
        elif close < pre_close and ratio20 >= Decimal("1.50"):
            volume_pattern = "放量下跌"
        elif ratio20 <= Decimal("0.70"):
            volume_pattern = "缩量整理"
        else:
            volume_pattern = "量能平稳"

        fee_total = self._fee_total(trade)
        turnover = Decimal(str(trade.price)) * Decimal(str(trade.quantity))
        execution_quality = "clean" if fee_total == 0 else "costly"
        volume_chart = []
        for index, item in enumerate(bars):
            window_5 = [Decimal(str(bar["volume"])) for bar in bars[max(0, index - 4) : index + 1]]
            window_10 = [Decimal(str(bar["volume"])) for bar in bars[max(0, index - 9) : index + 1]]
            window_20 = [Decimal(str(bar["volume"])) for bar in bars[max(0, index - 19) : index + 1]]
            volume_chart.append(
                {
                    "trade_date": item["trade_date"],
                    "volume": float(Decimal(str(item["volume"]))),
                    "avg_volume_5": float(self._average(window_5).quantize(Decimal("0.0001"))),
                    "avg_volume_10": float(self._average(window_10).quantize(Decimal("0.0001"))),
                    "avg_volume_20": float(self._average(window_20).quantize(Decimal("0.0001"))),
                }
            )
        return {
            "trade_quantity": int(Decimal(str(trade.quantity))),
            "trade_price": float(Decimal(str(trade.price))),
            "turnover": float(turnover),
            "fee_total": float(fee_total),
            "turnover_ratio": float(ratio20.quantize(Decimal("0.0001"))),
            "volume_ratio_5": float(ratio5.quantize(Decimal("0.0001"))),
            "volume_ratio_10": float(ratio10.quantize(Decimal("0.0001"))),
            "volume_ratio_20": float(ratio20.quantize(Decimal("0.0001"))),
            "daily_volume": float(target_volume),
            "daily_amount": float(amount),
            "volume_signal": volume_signal,
            "volume_pattern": volume_pattern,
            "execution_quality": execution_quality,
            "volume_chart": volume_chart,
            "data_source": target_bar.get("data_source") or getattr(self.market_api, "provider_name", "market_api"),
            "degraded": False,
            "degraded_reason": "",
        }

    def _fallback_analysis(self, trade, degraded_reason: str | None = None):
        price = Decimal(str(trade.price))
        quantity = Decimal(str(trade.quantity))
        turnover = price * quantity
        fee_total = self._fee_total(trade)
        avg_turnover = self._market_average_turnover(trade.market)
        turnover_ratio = (turnover / avg_turnover) if avg_turnover > 0 else Decimal("0")

        if turnover_ratio >= Decimal("1.50"):
            volume_signal = "high"
        elif turnover_ratio <= Decimal("0.50"):
            volume_signal = "low"
        else:
            volume_signal = "normal"

        execution_quality = "clean" if fee_total == 0 else "costly"
        return {
            "trade_quantity": int(quantity),
            "trade_price": float(price),
            "turnover": float(turnover),
            "fee_total": float(fee_total),
            "turnover_ratio": float(turnover_ratio.quantize(Decimal("0.0001"))),
            "volume_signal": volume_signal,
            "volume_pattern": "启发式估算",
            "execution_quality": execution_quality,
            "volume_chart": [],
            "data_source": "fallback_heuristic",
            "degraded": True,
            "degraded_reason": degraded_reason or self._default_degraded_reason(trade),
        }

    def _fee_total(self, trade) -> Decimal:
        return (
            Decimal(str(getattr(trade, "commission", 0)))
            + Decimal(str(getattr(trade, "stamp_duty", 0)))
            + Decimal(str(getattr(trade, "other_fees", 0)))
        )

    def _market_average_turnover(self, market: str) -> Decimal:
        if market == TradeRecord.Market.HK_STOCK:
            return Decimal("5000")
        return Decimal("10000")

    def _average(self, values: list[Decimal]) -> Decimal:
        if not values:
            return Decimal("0")
        return sum(values) / Decimal(len(values))

    def _safe_ratio(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator <= 0:
            return Decimal("0")
        return numerator / denominator

    def _is_special_hk_etf(self, stock_code: str) -> bool:
        return str(stock_code).strip().upper() in SPECIAL_HK_ETF_CODES

    def _missing_bars_reason(self, trade) -> str:
        if trade.market == TradeRecord.Market.HK_STOCK:
            return "Tushare 未返回可用的港股日线数据。"
        return "Tushare 未返回可用的 A 股日线数据。"

    def _default_degraded_reason(self, trade) -> str:
        if trade.market == TradeRecord.Market.HK_STOCK and self._is_special_hk_etf(trade.stock_code):
            return "港股杠杆 ETF 当前缺少稳定历史数据源，使用降级估算。"
        if trade.market == TradeRecord.Market.HK_STOCK:
            return "港股当前未接入真实量能数据源，使用降级估算。"
        return "当前未接入真实 A 股量能数据源，使用降级估算。"
