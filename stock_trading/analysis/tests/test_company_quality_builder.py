from decimal import Decimal

import pandas as pd
from django.utils import timezone

from analysis.services.company_quality_builder import CompanyQualitySnapshotBuilder
from trades.models import TradeRecord


class FakeTushareClient:
    is_available = True

    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def call(self, method, cache_key=None, **kwargs):
        self.calls.append((method, kwargs))
        return self.frames.get(method)


def test_hk_company_quality_builder_uses_hk_financial_data():
    trade = TradeRecord(
        stock_code="00189",
        stock_name="东岳集团",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("12.3000"),
        quantity=2000,
        trade_time=timezone.now(),
        source=TradeRecord.Source.MANUAL,
    )
    builder = CompanyQualitySnapshotBuilder(
        tushare_client=FakeTushareClient(
            {
                "hk_daily": pd.DataFrame(
                    [
                        {
                            "ts_code": "00189.HK",
                            "trade_date": "20260427",
                            "open": 12.38,
                            "high": 12.64,
                            "low": 12.2,
                            "close": 12.46,
                            "pre_close": 12.3,
                            "change": 0.16,
                            "pct_chg": 1.3,
                            "vol": 13924000.0,
                            "amount": 173526000.0,
                        }
                    ]
                ),
                "hk_fina_indicator": pd.DataFrame(
                    [
                        {
                            "ts_code": "00189.HK",
                            "name": "东岳集团",
                            "end_date": "20251231",
                            "report_type": "2025年年报",
                            "basic_eps": 0.98,
                            "operate_income": 14355381000.0,
                            "operate_income_yoy": 12.5,
                            "gross_profit_ratio": 30.8,
                            "roe_avg": 14.2,
                            "debt_asset_ratio": 38.5,
                            "current_ratio": 1.82,
                            "pe_ttm": 14.8,
                            "pb_ttm": 2.3,
                            "netcash_operate": 3050000000.0,
                            "total_assets": 22500000000.0,
                            "total_liabilities": 8662500000.0,
                        }
                    ]
                ),
                "hk_basic": pd.DataFrame(
                    [
                        {
                            "ts_code": "00189.HK",
                            "name": "东岳集团",
                            "fullname": "东岳集团有限公司",
                            "enname": "Dongyue Group Ltd.",
                            "market": "主板",
                            "list_status": "L",
                            "list_date": "20071210",
                        }
                    ]
                ),
            }
        )
    )

    result = builder.build(trade)

    assert result["ts_code"] == "00189.HK"
    assert result["trade_date"] == "20260427"
    assert result["valuation_band"] == "low"
    assert result["profitability"] == "solid"
    assert result["growth_status"] == "steady"
    assert result["balance_sheet_strength"] == "stable"
    assert result["company_profile"]["name"] == "东岳集团"
    assert result["metrics"]["pe_ttm"] == 14.8
    assert result["metrics"]["roe"] == 14.2
    assert result["degraded"] is False
