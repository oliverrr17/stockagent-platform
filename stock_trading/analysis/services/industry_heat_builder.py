from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from trades.models import TradeRecord

from .tushare_support import TushareProAdapter, normalize_a_share_code


class IndustryHeatSnapshotBuilder:
    def __init__(self, tushare_client: TushareProAdapter | None = None, market_api=None):
        self.tushare_client = tushare_client or TushareProAdapter()
        self.market_api = market_api

    def build(self, trade):
        if trade.market == TradeRecord.Market.HK_STOCK:
            return self._build_hk_industry_snapshot(trade)
        if trade.market != TradeRecord.Market.A_STOCK:
            return self._unknown_snapshot(trade, "industry_heat_not_supported_for_market")
        if not self.tushare_client.is_available:
            return self._unknown_snapshot(trade, "tushare_not_configured")

        trade_day = trade.trade_time.date()
        industry_map = self._industry_map()
        if not industry_map:
            return self._unknown_snapshot(trade, "industry_index_catalog_missing")

        members = self.tushare_client.call(
            "ths_member",
            cache_key="industry_heat:ths_member:all",
        )
        con_code = normalize_a_share_code(trade.stock_code)
        matched = members[members["con_code"] == con_code] if members is not None else None
        if matched is None or len(matched) == 0:
            return self._unknown_snapshot(trade, "industry_member_mapping_missing")

        industry_code = str(matched.iloc[0]["ts_code"])
        industry_meta = industry_map.get(industry_code, {"name": industry_code})
        return self._build_snapshot_from_index(
            trade,
            industry_code=industry_code,
            industry_name=industry_meta["name"],
            daily_method="ths_daily",
            cache_prefix="industry_heat:ths_daily",
        )

    def _build_hk_industry_snapshot(self, trade):
        if not self.tushare_client.is_available:
            return self._unknown_snapshot(trade, "tushare_not_configured")

        trade_day = trade.trade_time.date()
        industry_map = self._hk_industry_map()
        if not industry_map:
            return self._unknown_snapshot(trade, "industry_index_catalog_missing")

        normalized_target = self._normalize_hk_member_code(trade.stock_code)
        matched = None
        for industry_code, meta in industry_map.items():
            members = self.tushare_client.call(
                "ths_member",
                cache_key=f"industry_heat:hk:ths_member:{industry_code}",
                ts_code=industry_code,
            )
            if members is None or len(members) == 0:
                continue
            candidates = members["con_code"].astype(str).tolist()
            if any(self._normalize_hk_member_code(code) == normalized_target for code in candidates):
                matched = (industry_code, meta["name"])
                break

        if matched is None:
            return self._unknown_snapshot(trade, "industry_member_mapping_missing")

        industry_code, industry_name = matched
        return self._build_snapshot_from_index(
            trade,
            industry_code=industry_code,
            industry_name=industry_name,
            daily_method="ths_daily",
            cache_prefix="industry_heat:hk:ths_daily",
        )

    def _build_snapshot_from_index(self, trade, *, industry_code: str, industry_name: str, daily_method: str, cache_prefix: str):
        trade_day = trade.trade_time.date()
        start = (trade_day - timedelta(days=10)).strftime("%Y%m%d")
        end = trade_day.strftime("%Y%m%d")
        daily = self.tushare_client.call(
            daily_method,
            cache_key=f"{cache_prefix}:{industry_code}:{trade_day.isoformat()}",
            ts_code=industry_code,
            start_date=start,
            end_date=end,
        )
        if daily is None or len(daily) == 0:
            return self._unknown_snapshot(trade, "industry_daily_data_missing")

        latest = daily.iloc[0]
        pct_change = self._to_decimal(latest.get("pct_change"))
        turnover_rate = self._to_decimal(latest.get("turnover_rate"))
        industry_return_5d = self._window_return(daily, 5)
        stock_return_5d = self._stock_window_return(trade, trade_day)

        if pct_change >= Decimal("1") or industry_return_5d >= Decimal("3"):
            heat_level = "hot"
        elif pct_change <= Decimal("-1") or industry_return_5d <= Decimal("-3"):
            heat_level = "cold"
        else:
            heat_level = "neutral"

        security_position = "unknown"
        degraded = False
        degraded_reason = ""
        if stock_return_5d is None:
            degraded = True
            degraded_reason = "stock_daily_bars_unavailable"
        else:
            if stock_return_5d >= industry_return_5d + Decimal("2"):
                security_position = "leading"
            elif stock_return_5d <= industry_return_5d - Decimal("2"):
                security_position = "lagging"
            else:
                security_position = "in_line"

        return {
            "industry_ts_code": industry_code,
            "industry_name": industry_name,
            "trade_date": str(latest.get("trade_date")),
            "pct_change": float(pct_change),
            "turnover_rate": float(turnover_rate),
            "industry_return_5d": float(industry_return_5d),
            "stock_return_5d": float(stock_return_5d) if stock_return_5d is not None else None,
            "heat_level": heat_level,
            "security_position": security_position,
            "degraded": degraded,
            "degraded_reason": degraded_reason,
        }

    def _industry_map(self):
        indices = self.tushare_client.call(
            "ths_index",
            cache_key="industry_heat:ths_index:type_i",
            exchange="A",
            type="I",
        )
        if indices is None or len(indices) == 0:
            return {}
        return {
            str(row["ts_code"]): {"name": str(row["name"]), "type": str(row["type"])}
            for row in indices.to_dict("records")
        }

    def _hk_industry_map(self):
        indices = self.tushare_client.call(
            "ths_index",
            cache_key="industry_heat:hk:ths_index:type_i",
            exchange="HK",
            type="I",
        )
        if indices is None or len(indices) == 0:
            return {}
        return {
            str(row["ts_code"]): {"name": str(row["name"]), "type": str(row["type"])}
            for row in indices.to_dict("records")
        }

    def _stock_window_return(self, trade, trade_day):
        if self.market_api is None:
            return None
        start = trade_day - timedelta(days=10)
        end = trade_day
        try:
            bars = self.market_api.fetch_daily_bars(trade.stock_code, start=start, end=end, market=trade.market)
        except Exception:
            return None
        if not bars:
            return None
        closes = [self._to_decimal(item.get("close")) for item in bars if item.get("close") is not None]
        if len(closes) < 2:
            return Decimal("0")
        current = closes[-1]
        baseline = closes[-5] if len(closes) >= 5 else closes[0]
        if baseline == 0:
            return Decimal("0")
        return ((current - baseline) / baseline * Decimal("100")).quantize(Decimal("0.0001"))

    def _window_return(self, frame, lookback: int):
        closes = [self._to_decimal(item["close"]) for item in frame.to_dict("records")]
        if len(closes) < 2:
            return Decimal("0")
        current = closes[0]
        baseline = closes[min(lookback - 1, len(closes) - 1)]
        if baseline == 0:
            return Decimal("0")
        return ((current - baseline) / baseline * Decimal("100")).quantize(Decimal("0.0001"))

    def _unknown_snapshot(self, trade, reason: str):
        return {
            "industry_ts_code": "",
            "industry_name": "",
            "trade_date": trade.trade_time.date().isoformat(),
            "pct_change": None,
            "turnover_rate": None,
            "industry_return_5d": None,
            "stock_return_5d": None,
            "heat_level": "unknown",
            "security_position": "unknown",
            "degraded": True,
            "degraded_reason": reason,
        }

    def _normalize_hk_member_code(self, stock_code: str) -> str:
        text = str(stock_code).strip().upper().replace(".HK", "")
        if not text:
            return ""
        return text.zfill(5) + ".HK"

    def _to_decimal(self, value):
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))
