from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from trades.models import TradeRecord

from .tushare_support import TushareProAdapter, normalize_a_share_code


class CompanyQualitySnapshotBuilder:
    def __init__(self, tushare_client: TushareProAdapter | None = None):
        self.tushare_client = tushare_client or TushareProAdapter()

    def build(self, trade):
        if trade.market == TradeRecord.Market.HK_STOCK:
            return self._build_hk_quality_snapshot(trade)
        if trade.market != TradeRecord.Market.A_STOCK:
            return self._unknown_snapshot(trade, "company_quality_not_supported_for_market")
        if not self.tushare_client.is_available:
            return self._unknown_snapshot(trade, "tushare_not_configured")

        ts_code = normalize_a_share_code(trade.stock_code)
        trade_day = trade.trade_time.date()
        start = (trade_day - timedelta(days=10)).strftime("%Y%m%d")
        end = trade_day.strftime("%Y%m%d")

        daily_basic = self.tushare_client.call(
            "daily_basic",
            cache_key=f"company_quality:daily_basic:{ts_code}:{trade_day.isoformat()}",
            ts_code=ts_code,
            start_date=start,
            end_date=end,
        )
        fina_indicator = self.tushare_client.call(
            "fina_indicator",
            cache_key=f"company_quality:fina_indicator:{ts_code}",
            ts_code=ts_code,
            limit=1,
        )
        income = self.tushare_client.call(
            "income",
            cache_key=f"company_quality:income:{ts_code}",
            ts_code=ts_code,
            limit=1,
        )
        company = self._company_info(ts_code)

        if daily_basic is None or fina_indicator is None or len(daily_basic) == 0 or len(fina_indicator) == 0:
            return self._unknown_snapshot(trade, "company_quality_core_data_missing")

        basic_row = daily_basic.iloc[0]
        fina_row = fina_indicator.iloc[0]
        income_row = income.iloc[0] if income is not None and len(income) > 0 else None

        pe_ttm = self._optional_decimal(basic_row.get("pe_ttm"))
        pb = self._optional_decimal(basic_row.get("pb"))
        roe = self._optional_decimal(fina_row.get("roe"))
        gross_margin = self._optional_decimal(fina_row.get("grossprofit_margin"))
        debt_to_assets = self._optional_decimal(fina_row.get("debt_to_assets"))
        current_ratio = self._optional_decimal(fina_row.get("current_ratio"))
        quick_ratio = self._optional_decimal(fina_row.get("quick_ratio"))
        revenue = self._optional_decimal(income_row.get("revenue")) if income_row is not None else None
        revenue_ps = self._optional_decimal(fina_row.get("revenue_ps"))
        growth_metric = self._optional_decimal(
            fina_row.get("q_gr_yoy") if "q_gr_yoy" in fina_row else fina_row.get("tr_yoy")
        )

        if pe_ttm is None:
            valuation_band = "unknown"
        elif pe_ttm <= Decimal("18") and (pb is None or pb <= Decimal("4")):
            valuation_band = "low"
        elif pe_ttm >= Decimal("35") or (pb is not None and pb >= Decimal("8")):
            valuation_band = "high"
        else:
            valuation_band = "fair"

        if roe is not None and gross_margin is not None and roe >= Decimal("15") and gross_margin >= Decimal("30"):
            profitability = "strong"
        elif roe is not None and roe >= Decimal("8"):
            profitability = "solid"
        else:
            profitability = "weak"

        if growth_metric is None:
            growth_status = "unknown"
        elif growth_metric >= Decimal("20"):
            growth_status = "fast"
        elif growth_metric >= Decimal("5"):
            growth_status = "steady"
        else:
            growth_status = "slow"

        if debt_to_assets is not None and current_ratio is not None and quick_ratio is not None:
            if debt_to_assets <= Decimal("40") and current_ratio >= Decimal("1.5") and quick_ratio >= Decimal("1"):
                balance_sheet_strength = "stable"
            elif debt_to_assets >= Decimal("65"):
                balance_sheet_strength = "fragile"
            else:
                balance_sheet_strength = "mixed"
        else:
            balance_sheet_strength = "unknown"

        return {
            "ts_code": ts_code,
            "trade_date": str(basic_row.get("trade_date")),
            "valuation_band": valuation_band,
            "profitability": profitability,
            "growth_status": growth_status,
            "balance_sheet_strength": balance_sheet_strength,
            "metrics": {
                "pe_ttm": float(pe_ttm) if pe_ttm is not None else None,
                "pb": float(pb) if pb is not None else None,
                "roe": float(roe) if roe is not None else None,
                "grossprofit_margin": float(gross_margin) if gross_margin is not None else None,
                "debt_to_assets": float(debt_to_assets) if debt_to_assets is not None else None,
                "current_ratio": float(current_ratio) if current_ratio is not None else None,
                "quick_ratio": float(quick_ratio) if quick_ratio is not None else None,
                "growth_metric": float(growth_metric) if growth_metric is not None else None,
                "revenue": float(revenue) if revenue is not None else None,
                "revenue_ps": float(revenue_ps) if revenue_ps is not None else None,
            },
            "company_profile": company,
            "degraded": False,
            "degraded_reason": "",
        }

    def _build_hk_quality_snapshot(self, trade):
        if not self.tushare_client.is_available:
            return self._unknown_snapshot(trade, "tushare_not_configured")

        ts_code = self._normalize_hk_ts_code(trade.stock_code)
        trade_day = trade.trade_time.date()
        start = (trade_day - timedelta(days=10)).strftime("%Y%m%d")
        end = trade_day.strftime("%Y%m%d")

        daily = self.tushare_client.call(
            "hk_daily",
            cache_key=f"company_quality:hk_daily:{ts_code}:{trade_day.isoformat()}",
            ts_code=ts_code,
            start_date=start,
            end_date=end,
        )
        fina_indicator = self.tushare_client.call(
            "hk_fina_indicator",
            cache_key=f"company_quality:hk_fina_indicator:{ts_code}",
            ts_code=ts_code,
            limit=1,
        )
        company = self._hk_company_info(ts_code)

        if daily is None or fina_indicator is None or len(daily) == 0 or len(fina_indicator) == 0:
            return self._unknown_snapshot(trade, "company_quality_core_data_missing")

        daily_row = daily.iloc[0]
        fina_row = fina_indicator.iloc[0]

        pe_ttm = self._optional_decimal(fina_row.get("pe_ttm"))
        pb = self._optional_decimal(fina_row.get("pb_ttm"))
        roe = self._optional_decimal(fina_row.get("roe_avg"))
        gross_margin = self._optional_decimal(fina_row.get("gross_profit_ratio"))
        debt_to_assets = self._optional_decimal(fina_row.get("debt_asset_ratio"))
        current_ratio = self._optional_decimal(fina_row.get("current_ratio"))
        revenue = self._optional_decimal(fina_row.get("operate_income"))
        growth_metric = self._optional_decimal(fina_row.get("operate_income_yoy"))
        netcash_operate = self._optional_decimal(fina_row.get("netcash_operate"))
        total_assets = self._optional_decimal(fina_row.get("total_assets"))
        total_liabilities = self._optional_decimal(fina_row.get("total_liabilities"))

        if pe_ttm is None:
            valuation_band = "unknown"
        elif pe_ttm <= Decimal("18") and (pb is None or pb <= Decimal("4")):
            valuation_band = "low"
        elif pe_ttm >= Decimal("35") or (pb is not None and pb >= Decimal("8")):
            valuation_band = "high"
        else:
            valuation_band = "fair"

        if roe is not None and gross_margin is not None and roe >= Decimal("15") and gross_margin >= Decimal("30"):
            profitability = "strong"
        elif roe is not None and roe >= Decimal("8"):
            profitability = "solid"
        else:
            profitability = "weak"

        if growth_metric is None:
            growth_status = "unknown"
        elif growth_metric >= Decimal("20"):
            growth_status = "fast"
        elif growth_metric >= Decimal("5"):
            growth_status = "steady"
        else:
            growth_status = "slow"

        if debt_to_assets is not None and current_ratio is not None:
            if debt_to_assets <= Decimal("40") and current_ratio >= Decimal("1.5"):
                balance_sheet_strength = "stable"
            elif debt_to_assets >= Decimal("65"):
                balance_sheet_strength = "fragile"
            else:
                balance_sheet_strength = "mixed"
        else:
            balance_sheet_strength = "unknown"

        return {
            "ts_code": ts_code,
            "trade_date": str(daily_row.get("trade_date")),
            "valuation_band": valuation_band,
            "profitability": profitability,
            "growth_status": growth_status,
            "balance_sheet_strength": balance_sheet_strength,
            "metrics": {
                "pe_ttm": float(pe_ttm) if pe_ttm is not None else None,
                "pb": float(pb) if pb is not None else None,
                "roe": float(roe) if roe is not None else None,
                "grossprofit_margin": float(gross_margin) if gross_margin is not None else None,
                "debt_to_assets": float(debt_to_assets) if debt_to_assets is not None else None,
                "current_ratio": float(current_ratio) if current_ratio is not None else None,
                "quick_ratio": None,
                "growth_metric": float(growth_metric) if growth_metric is not None else None,
                "revenue": float(revenue) if revenue is not None else None,
                "revenue_ps": None,
                "netcash_operate": float(netcash_operate) if netcash_operate is not None else None,
                "total_assets": float(total_assets) if total_assets is not None else None,
                "total_liabilities": float(total_liabilities) if total_liabilities is not None else None,
            },
            "company_profile": company,
            "degraded": False,
            "degraded_reason": "",
        }

    def _company_info(self, ts_code: str):
        exchange = "SSE" if ts_code.endswith(".SH") else "SZSE"
        frame = self.tushare_client.call(
            "stock_company",
            cache_key=f"company_quality:stock_company:{exchange}",
            exchange=exchange,
        )
        if frame is None or len(frame) == 0:
            return {"name": "", "province": "", "city": "", "introduction": ""}
        matched = frame[frame["ts_code"] == ts_code]
        if len(matched) == 0:
            return {"name": "", "province": "", "city": "", "introduction": ""}
        row = matched.iloc[0]
        introduction = str(row.get("introduction") or "").strip()
        return {
            "name": str(row.get("com_name") or ""),
            "province": str(row.get("province") or ""),
            "city": str(row.get("city") or ""),
            "introduction": introduction[:180],
        }

    def _hk_company_info(self, ts_code: str):
        frame = self.tushare_client.call(
            "hk_basic",
            cache_key="company_quality:hk_basic:all",
        )
        if frame is None or len(frame) == 0:
            return {"name": "", "province": "", "city": "", "introduction": ""}
        matched = frame[frame["ts_code"] == ts_code]
        if len(matched) == 0:
            return {"name": "", "province": "", "city": "", "introduction": ""}
        row = matched.iloc[0]
        return {
            "name": str(row.get("name") or ""),
            "province": str(row.get("market") or ""),
            "city": str(row.get("list_status") or ""),
            "introduction": str(row.get("fullname") or row.get("enname") or "")[:180],
        }

    def _unknown_snapshot(self, trade, reason: str):
        return {
            "ts_code": "",
            "trade_date": trade.trade_time.date().isoformat(),
            "valuation_band": "unknown",
            "profitability": "unknown",
            "growth_status": "unknown",
            "balance_sheet_strength": "unknown",
            "metrics": {},
            "company_profile": {"name": "", "province": "", "city": "", "introduction": ""},
            "degraded": True,
            "degraded_reason": reason,
        }

    def _optional_decimal(self, value):
        if value in (None, ""):
            return None
        return Decimal(str(value))

    def _normalize_hk_ts_code(self, stock_code: str) -> str:
        code = str(stock_code).strip().upper()
        if code.endswith(".HK"):
            return code
        return f"{code}.HK"
