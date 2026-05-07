from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from trades.models import TradeRecord

from .tushare_support import TushareProAdapter


class MarketHeatSnapshotBuilder:
    BENCHMARK_TS_CODE = "000001.SH"

    def __init__(self, tushare_client: TushareProAdapter | None = None):
        self.tushare_client = tushare_client or TushareProAdapter()

    def build(self, trade):
        if trade.market == TradeRecord.Market.HK_STOCK:
            return self._build_hk_snapshot(trade)
        if trade.market != TradeRecord.Market.A_STOCK:
            return self._unknown_snapshot(trade, "market_heat_not_supported_for_market")
        if not self.tushare_client.is_available:
            return self._unknown_snapshot(trade, "tushare_not_configured")

        trade_day = trade.trade_time.date()
        start = (trade_day - timedelta(days=10)).strftime("%Y%m%d")
        end = trade_day.strftime("%Y%m%d")
        daily = self.tushare_client.call(
            "index_daily",
            cache_key=f"market_heat:index_daily:{trade_day.isoformat()}",
            ts_code=self.BENCHMARK_TS_CODE,
            start_date=start,
            end_date=end,
        )
        basic = self.tushare_client.call(
            "index_dailybasic",
            cache_key=f"market_heat:index_dailybasic:{trade_day.isoformat()}",
            ts_code=self.BENCHMARK_TS_CODE,
            start_date=start,
            end_date=end,
        )
        flow = self.tushare_client.call(
            "moneyflow_hsgt",
            cache_key=f"market_heat:moneyflow_hsgt:{trade_day.isoformat()}",
            start_date=start,
            end_date=end,
        )
        if daily is None or basic is None or len(daily) == 0 or len(basic) == 0:
            return self._unknown_snapshot(trade, "market_heat_daily_data_missing")

        daily_row = daily.iloc[0]
        basic_row = basic.iloc[0]
        flow_row = flow.iloc[0] if flow is not None and len(flow) > 0 else None

        pct_change = self._to_decimal(daily_row.get("pct_chg"))
        turnover_rate = self._to_decimal(basic_row.get("turnover_rate"))
        north_money = self._to_decimal(flow_row.get("north_money")) if flow_row is not None else None

        if pct_change >= Decimal("1") and (north_money is None or north_money >= 0):
            risk_preference = "risk_on"
        elif pct_change <= Decimal("-1") and (north_money is None or north_money < 0):
            risk_preference = "risk_off"
        else:
            risk_preference = "neutral"

        if turnover_rate >= Decimal("1.2"):
            activity_level = "active"
        elif turnover_rate >= Decimal("0.8"):
            activity_level = "normal"
        else:
            activity_level = "quiet"

        return {
            "market": trade.market,
            "benchmark_ts_code": self.BENCHMARK_TS_CODE,
            "benchmark_name": "上证指数",
            "trade_date": str(daily_row.get("trade_date")),
            "pct_change": float(pct_change),
            "close": float(self._to_decimal(daily_row.get("close"))),
            "turnover_rate": float(turnover_rate),
            "north_money": float(north_money) if north_money is not None else None,
            "risk_preference": risk_preference,
            "activity_level": activity_level,
            "degraded": False,
            "degraded_reason": "",
        }

    def _build_hk_snapshot(self, trade):
        if not self.tushare_client.is_available:
            return self._unknown_snapshot(trade, "tushare_not_configured")

        trade_day = trade.trade_time.date()
        start = (trade_day - timedelta(days=10)).strftime("%Y%m%d")
        end = trade_day.strftime("%Y%m%d")
        flow = self.tushare_client.call(
            "ggt_daily",
            cache_key=f"market_heat:ggt_daily:{trade_day.isoformat()}",
            start_date=start,
            end_date=end,
        )
        hold = self.tushare_client.call(
            "hk_hold",
            cache_key=f"market_heat:hk_hold:{trade_day.isoformat()}",
            trade_date=trade_day.strftime("%Y%m%d"),
        )
        if flow is None or len(flow) == 0:
            return self._unknown_snapshot(trade, "market_heat_hk_flow_missing")

        flow_row = flow.iloc[0]
        buy_amount = self._to_decimal(flow_row.get("buy_amount"))
        sell_amount = self._to_decimal(flow_row.get("sell_amount"))
        net_flow = buy_amount - sell_amount
        total_flow = buy_amount + sell_amount

        if net_flow >= Decimal("20"):
            risk_preference = "risk_on"
        elif net_flow <= Decimal("-20"):
            risk_preference = "risk_off"
        else:
            risk_preference = "neutral"

        if total_flow >= Decimal("500"):
            activity_level = "active"
        elif total_flow >= Decimal("200"):
            activity_level = "normal"
        else:
            activity_level = "quiet"

        holdings_count = len(hold) if hold is not None else 0
        avg_hold_ratio = None
        if hold is not None and len(hold) > 0 and "ratio" in hold.columns:
            ratios = []
            for value in hold["ratio"].tolist():
                decimal_value = self._to_decimal(value)
                if decimal_value.is_nan():
                    continue
                ratios.append(decimal_value)
            if ratios:
                avg_hold_ratio = (sum(ratios) / Decimal(len(ratios))).quantize(Decimal("0.0001"))

        return {
            "market": trade.market,
            "benchmark_ts_code": "southbound_connect",
            "benchmark_name": "港股通南向资金",
            "trade_date": str(flow_row.get("trade_date")),
            "pct_change": None,
            "close": None,
            "turnover_rate": None,
            "north_money": None,
            "buy_amount": float(buy_amount),
            "sell_amount": float(sell_amount),
            "net_flow": float(net_flow.quantize(Decimal("0.0001"))),
            "holdings_count": int(holdings_count),
            "avg_hold_ratio": float(avg_hold_ratio) if avg_hold_ratio is not None else None,
            "risk_preference": risk_preference,
            "activity_level": activity_level,
            "degraded": False,
            "degraded_reason": "",
        }

    def _unknown_snapshot(self, trade, reason: str):
        return {
            "market": trade.market,
            "benchmark_ts_code": "",
            "benchmark_name": "",
            "trade_date": trade.trade_time.date().isoformat(),
            "pct_change": None,
            "close": None,
            "turnover_rate": None,
            "north_money": None,
            "buy_amount": None,
            "sell_amount": None,
            "net_flow": None,
            "holdings_count": None,
            "avg_hold_ratio": None,
            "risk_preference": "unknown",
            "activity_level": "unknown",
            "degraded": True,
            "degraded_reason": reason,
        }

    def _to_decimal(self, value):
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))
