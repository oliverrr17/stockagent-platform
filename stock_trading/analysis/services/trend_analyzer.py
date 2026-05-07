from __future__ import annotations

from decimal import Decimal

from analysis.services.market_data import SPECIAL_HK_ETF_CODES, trade_date_window
from trades.models import TradeRecord


class TrendAnalyzer:
    def __init__(self, market_api=None):
        self.market_api = market_api

    def analyze(self, trade):
        if self.market_api and trade.market == TradeRecord.Market.A_STOCK:
            return self._analyze_with_daily_bars(trade)
        if self.market_api and trade.market == TradeRecord.Market.HK_STOCK and not self._is_special_hk_etf(trade.stock_code):
            return self._analyze_with_daily_bars(trade)
        return self._fallback_analysis(trade)

    def calculate_moving_averages(self, prices):
        raise NotImplementedError("Detailed moving-average calculation is not implemented yet.")

    def calculate_indicators(self, klines):
        raise NotImplementedError("Detailed technical indicator calculation is not implemented yet.")

    def identify_trend_phase(self, klines):
        raise NotImplementedError("Detailed trend phase identification is not implemented yet.")

    def find_support_resistance(self, klines):
        raise NotImplementedError("Detailed support/resistance calculation is not implemented yet.")

    def _analyze_with_daily_bars(self, trade):
        lookback_days = 180 if trade.market == TradeRecord.Market.A_STOCK else 240
        start, end = trade_date_window(trade.trade_time, lookback_days=lookback_days)
        bars = self.market_api.fetch_daily_bars(trade.stock_code, start=start, end=end, market=trade.market)
        if len(bars) < 10:
            return self._fallback_analysis(trade, degraded_reason=self._missing_bars_reason(trade))

        closes = [Decimal(str(item["close"])) for item in bars]
        highs = [Decimal(str(item["high"])) for item in bars]
        lows = [Decimal(str(item["low"])) for item in bars]
        close = closes[-1]
        ma5 = self._moving_average(closes, 5)
        ma10 = self._moving_average(closes, 10)
        ma20 = self._moving_average(closes, 20)
        ma60 = self._moving_average(closes, 60)
        macd_line, signal_line, macd_hist = self._macd(closes)
        rsi14 = self._rsi(closes, 14)
        k_value, d_value, j_value = self._kdj(highs, lows, closes, 9)
        support = min(lows[-20:])
        resistance = max(highs[-20:])

        if close >= resistance * Decimal("0.995") and ma5 >= ma10 >= ma20:
            trend_phase = "breakout_attempt"
        elif ma5 >= ma10 >= ma20 and close >= ma20:
            trend_phase = "uptrend"
        elif close >= ma10 and macd_hist >= 0:
            trend_phase = "rebound"
        elif ma5 < ma20:
            trend_phase = "profit_taking"
        else:
            trend_phase = "range_bound"

        price_chart = []
        for index, item in enumerate(bars):
            close_series = closes[: index + 1]
            price_chart.append(
                {
                    "trade_date": item["trade_date"],
                    "open": float(Decimal(str(item["open"]))),
                    "high": float(Decimal(str(item["high"]))),
                    "low": float(Decimal(str(item["low"]))),
                    "close": float(Decimal(str(item["close"]))),
                    "ma5": float(self._moving_average(close_series, 5).quantize(Decimal("0.0001"))),
                    "ma10": float(self._moving_average(close_series, 10).quantize(Decimal("0.0001"))),
                    "ma20": float(self._moving_average(close_series, 20).quantize(Decimal("0.0001"))),
                    "support": float(support.quantize(Decimal("0.0001"))),
                    "resistance": float(resistance.quantize(Decimal("0.0001"))),
                }
            )

        return {
            "trade_price": float(close),
            "trend_phase": trend_phase,
            "support_levels": [float(support.quantize(Decimal("0.0001")))],
            "resistance_levels": [float(resistance.quantize(Decimal("0.0001")))],
            "distance_to_support_pct": float(((close - support) / close * Decimal("100")).quantize(Decimal("0.0001"))),
            "distance_to_resistance_pct": float(((resistance - close) / close * Decimal("100")).quantize(Decimal("0.0001"))),
            "ma5": float(ma5.quantize(Decimal("0.0001"))),
            "ma10": float(ma10.quantize(Decimal("0.0001"))),
            "ma20": float(ma20.quantize(Decimal("0.0001"))),
            "ma60": float(ma60.quantize(Decimal("0.0001"))),
            "macd": float(macd_line.quantize(Decimal("0.0001"))),
            "signal_line": float(signal_line.quantize(Decimal("0.0001"))),
            "macd_hist": float(macd_hist.quantize(Decimal("0.0001"))),
            "rsi14": float(rsi14.quantize(Decimal("0.0001"))),
            "k_value": float(k_value.quantize(Decimal("0.0001"))),
            "d_value": float(d_value.quantize(Decimal("0.0001"))),
            "j_value": float(j_value.quantize(Decimal("0.0001"))),
            "price_chart": price_chart,
            "data_source": bars[-1].get("data_source") or getattr(self.market_api, "provider_name", "market_api"),
            "degraded": False,
            "degraded_reason": "",
        }

    def _fallback_analysis(self, trade, degraded_reason: str | None = None):
        price = Decimal(str(trade.price))
        support = (price * Decimal("0.95")).quantize(Decimal("0.0001"))
        resistance = (price * Decimal("1.05")).quantize(Decimal("0.0001"))

        if trade.direction == TradeRecord.Direction.BUY:
            trend_phase = "breakout_attempt"
        else:
            trend_phase = "profit_taking"

        return {
            "trade_price": float(price),
            "trend_phase": trend_phase,
            "support_levels": [float(support)],
            "resistance_levels": [float(resistance)],
            "distance_to_support_pct": float(((price - support) / price * Decimal("100")).quantize(Decimal("0.0001"))),
            "distance_to_resistance_pct": float(((resistance - price) / price * Decimal("100")).quantize(Decimal("0.0001"))),
            "price_chart": [],
            "data_source": "fallback_heuristic",
            "degraded": True,
            "degraded_reason": degraded_reason or self._default_degraded_reason(trade),
        }

    def _moving_average(self, values: list[Decimal], window: int) -> Decimal:
        if not values:
            return Decimal("0")
        selected = values[-window:] if len(values) >= window else values
        return sum(selected) / Decimal(len(selected))

    def _ema(self, values: list[Decimal], period: int) -> Decimal:
        if not values:
            return Decimal("0")
        multiplier = Decimal("2") / Decimal(period + 1)
        ema = values[0]
        for value in values[1:]:
            ema = (value - ema) * multiplier + ema
        return ema

    def _macd(self, closes: list[Decimal]):
        ema12_series = self._ema_series(closes, 12)
        ema26_series = self._ema_series(closes, 26)
        macd_series = [left - right for left, right in zip(ema12_series, ema26_series)]
        signal_series = self._ema_series(macd_series, 9)
        macd_line = macd_series[-1]
        signal_line = signal_series[-1]
        return macd_line, signal_line, macd_line - signal_line

    def _ema_series(self, values: list[Decimal], period: int):
        multiplier = Decimal("2") / Decimal(period + 1)
        ema = values[0]
        series = [ema]
        for value in values[1:]:
            ema = (value - ema) * multiplier + ema
            series.append(ema)
        return series

    def _rsi(self, closes: list[Decimal], period: int):
        if len(closes) <= 1:
            return Decimal("50")
        deltas = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
        selected = deltas[-period:] if len(deltas) >= period else deltas
        gains = [delta for delta in selected if delta > 0]
        losses = [abs(delta) for delta in selected if delta < 0]
        average_gain = (sum(gains) / Decimal(len(selected))) if selected else Decimal("0")
        average_loss = (sum(losses) / Decimal(len(selected))) if selected else Decimal("0")
        if average_loss == 0:
            return Decimal("100") if average_gain > 0 else Decimal("50")
        rs = average_gain / average_loss
        return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

    def _kdj(self, highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], period: int):
        selected_highs = highs[-period:] if len(highs) >= period else highs
        selected_lows = lows[-period:] if len(lows) >= period else lows
        high_n = max(selected_highs)
        low_n = min(selected_lows)
        close = closes[-1]
        if high_n == low_n:
            rsv = Decimal("50")
        else:
            rsv = (close - low_n) / (high_n - low_n) * Decimal("100")
        k_value = Decimal("66.6667") * Decimal("2") / Decimal("3") + rsv / Decimal("3")
        d_value = Decimal("66.6667") * Decimal("2") / Decimal("3") + k_value / Decimal("3")
        j_value = Decimal("3") * k_value - Decimal("2") * d_value
        return k_value, d_value, j_value

    def _is_special_hk_etf(self, stock_code: str) -> bool:
        return str(stock_code).strip().upper() in SPECIAL_HK_ETF_CODES

    def _missing_bars_reason(self, trade) -> str:
        if trade.market == TradeRecord.Market.HK_STOCK:
            return "Tushare 未返回足够的港股日线数据。"
        return "Tushare 未返回足够的 A 股趋势日线数据。"

    def _default_degraded_reason(self, trade) -> str:
        if trade.market == TradeRecord.Market.HK_STOCK and self._is_special_hk_etf(trade.stock_code):
            return "港股杠杆 ETF 当前缺少稳定历史数据源，使用降级估算。"
        if trade.market == TradeRecord.Market.HK_STOCK:
            return "港股当前未接入真实趋势数据源，使用降级估算。"
        return "当前未接入真实 A 股趋势数据源，使用降级估算。"
