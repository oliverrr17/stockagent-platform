from __future__ import annotations

from decimal import Decimal

from analysis.services.market_data import SPECIAL_HK_ETF_CODES, trade_date_window
from analysis.services.tushare_support import TushareProAdapter, normalize_a_share_code
from trades.models import TradeRecord


class ChipAnalyzer:
    def __init__(self, market_api=None, tushare_client: TushareProAdapter | None = None):
        self.market_api = market_api
        self.tushare_client = tushare_client or TushareProAdapter()

    def analyze(self, trade):
        if trade.market == TradeRecord.Market.A_STOCK and self.tushare_client.is_available:
            result = self._analyze_a_share_with_cyq(trade)
            if result is not None:
                return result

        if self.market_api and trade.market == TradeRecord.Market.HK_STOCK and not self._is_special_hk_etf(trade.stock_code):
            return self._analyze_hk_with_daily_bars(trade)

        return self._fallback_analysis(trade, degraded_reason=self._default_degraded_reason(trade))

    def calculate_chip_concentration(self, chip_data):
        raise NotImplementedError("Detailed chip concentration calculation is not implemented yet.")

    def locate_price_position(self, price, chip_data):
        raise NotImplementedError("Detailed chip position analysis is not implemented yet.")

    def _analyze_a_share_with_cyq(self, trade):
        trade_day = trade.trade_time.date()
        start, end = trade_date_window(trade.trade_time, lookback_days=30)
        ts_code = normalize_a_share_code(trade.stock_code)
        try:
            perf = self.tushare_client.call(
                "cyq_perf",
                cache_key=f"chip:cyq_perf:{ts_code}:{trade_day.isoformat()}",
                ts_code=ts_code,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            chips = self.tushare_client.call(
                "cyq_chips",
                cache_key=f"chip:cyq_chips:{ts_code}:{trade_day.isoformat()}",
                ts_code=ts_code,
                trade_date=trade_day.strftime("%Y%m%d"),
            )
        except Exception:
            return None

        if perf is None or len(perf) == 0:
            return None

        perf_row = perf.iloc[0]
        chips_rows = chips.to_dict("records") if chips is not None and len(chips) > 0 else []
        reference_price = self._resolve_reference_price(trade)
        cost_15 = self._to_decimal(perf_row.get("cost_15pct"))
        cost_50 = self._to_decimal(perf_row.get("cost_50pct"))
        cost_85 = self._to_decimal(perf_row.get("cost_85pct"))
        cost_5 = self._to_decimal(perf_row.get("cost_5pct"))
        cost_95 = self._to_decimal(perf_row.get("cost_95pct"))

        if reference_price <= cost_15:
            position_zone = "value_zone"
        elif reference_price >= cost_85:
            position_zone = "premium_zone"
        else:
            position_zone = "mid_zone"

        chip_concentration = self._estimate_chip_concentration(chips_rows)

        return {
            "reference_price": float(reference_price),
            "position_zone": position_zone,
            "chip_concentration": float(chip_concentration),
            "band_lower": float(cost_5),
            "band_upper": float(cost_95),
            "winner_rate": float(self._to_decimal(perf_row.get("winner_rate"))),
            "weight_avg": float(self._to_decimal(perf_row.get("weight_avg"))),
            "cost_50pct": float(cost_50),
            "data_source": "tushare_cyq",
            "degraded": False,
            "degraded_reason": "",
        }

    def _analyze_hk_with_daily_bars(self, trade):
        start, end = trade_date_window(trade.trade_time, lookback_days=180)
        bars = self.market_api.fetch_daily_bars(trade.stock_code, start=start, end=end, market=trade.market)
        if len(bars) < 2:
            return self._fallback_analysis(
                trade,
                degraded_reason="Tushare 未返回足够的港股日线数据，使用价格区间降级估算。",
            )

        relevant = bars[-60:] if len(bars) >= 60 else bars
        highs = [self._to_decimal(item["high"]) for item in relevant]
        lows = [self._to_decimal(item["low"]) for item in relevant]
        closes = [self._to_decimal(item["close"]) for item in relevant]
        reference_price = closes[-1]
        lower_bound = min(lows)
        upper_bound = max(highs)
        band_width = upper_bound - lower_bound
        relative = (reference_price - lower_bound) / band_width if band_width > 0 else Decimal("0")

        if relative <= Decimal("0.33"):
            position_zone = "value_zone"
        elif relative >= Decimal("0.66"):
            position_zone = "premium_zone"
        else:
            position_zone = "mid_zone"

        average_close = sum(closes) / Decimal(len(closes))
        avg_range_pct = sum(
            ((self._to_decimal(item["high"]) - self._to_decimal(item["low"])) / self._to_decimal(item["close"]))
            if self._to_decimal(item["close"]) > 0
            else Decimal("0")
            for item in relevant
        ) / Decimal(len(relevant))
        distance_from_average = abs(reference_price - average_close) / average_close if average_close > 0 else Decimal("0")
        chip_concentration = Decimal("1") - min((avg_range_pct + distance_from_average) * Decimal("2"), Decimal("1"))

        return {
            "reference_price": float(reference_price),
            "position_zone": position_zone,
            "chip_concentration": float(chip_concentration.quantize(Decimal("0.0001"))),
            "band_lower": float(lower_bound.quantize(Decimal("0.0001"))),
            "band_upper": float(upper_bound.quantize(Decimal("0.0001"))),
            "data_source": relevant[-1].get("data_source") or getattr(self.market_api, "provider_name", "market_api"),
            "degraded": True,
            "degraded_reason": "港股当前缺少真实筹码分布源，已基于 Tushare 日线价格区间估算。",
        }

    def _fallback_analysis(self, trade, degraded_reason: str):
        price = self._to_decimal(trade.price)
        lower_bound, upper_bound = self._price_band(trade.market)
        band_width = upper_bound - lower_bound
        relative = (price - lower_bound) / band_width if band_width > 0 else Decimal("0")

        if relative <= Decimal("0.33"):
            position_zone = "value_zone"
        elif relative >= Decimal("0.66"):
            position_zone = "premium_zone"
        else:
            position_zone = "mid_zone"

        chip_concentration = Decimal("1") - min(abs(relative - Decimal("0.5")) * Decimal("2"), Decimal("1"))
        return {
            "reference_price": float(price),
            "position_zone": position_zone,
            "chip_concentration": float(chip_concentration.quantize(Decimal("0.0001"))),
            "band_lower": float(lower_bound),
            "band_upper": float(upper_bound),
            "data_source": "fallback_heuristic",
            "degraded": True,
            "degraded_reason": degraded_reason,
        }

    def _price_band(self, market: str):
        if market == TradeRecord.Market.HK_STOCK:
            return Decimal("5"), Decimal("120")
        return Decimal("10"), Decimal("150")

    def _is_special_hk_etf(self, stock_code: str) -> bool:
        return str(stock_code).strip().upper() in SPECIAL_HK_ETF_CODES

    def _default_degraded_reason(self, trade) -> str:
        if trade.market == TradeRecord.Market.HK_STOCK and self._is_special_hk_etf(trade.stock_code):
            return "港股杠杆 ETF 当前缺少稳定历史筹码源，使用价格区间降级估算。"
        if trade.market == TradeRecord.Market.HK_STOCK:
            return "港股当前未接入真实筹码数据源，使用价格区间降级估算。"
        return "A股当前未接入真实筹码数据源，使用价格区间降级估算。"

    def _resolve_reference_price(self, trade):
        if self.market_api is not None:
            try:
                snapshot = self.market_api.get_snapshot(trade.stock_code, trade.market)
            except Exception:
                snapshot = {}
            latest_price = snapshot.get("latest_price") if isinstance(snapshot, dict) else None
            if latest_price not in (None, ""):
                return self._to_decimal(latest_price)
        return self._to_decimal(trade.price)

    def _estimate_chip_concentration(self, chips_rows):
        if not chips_rows:
            return Decimal("0")
        top_share = sorted(
            (self._to_decimal(item.get("percent")) for item in chips_rows),
            reverse=True,
        )[:10]
        return min(sum(top_share), Decimal("1")).quantize(Decimal("0.0001"))

    def _to_decimal(self, value):
        if value in (None, ""):
            return Decimal("0")
        return Decimal(str(value))
