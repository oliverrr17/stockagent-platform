from decimal import Decimal

import pytest

from trades.models import TradeRecord
from trades.services.futu_connector import FutuConnector


class FakeFutuAPI:
    def __init__(self, accounts, orders, fee_rows):
        self.accounts = accounts
        self.orders = orders
        self.fee_rows = fee_rows
        self.fee_query_batches = []

    def get_acc_list(self):
        return 0, self.accounts

    def history_order_list_query(self, **kwargs):
        return 0, self.orders

    def order_fee_query(self, order_id_list, **kwargs):
        self.fee_query_batches.append(list(order_id_list))
        return 0, self.fee_rows


def test_futu_connector_rejects_non_hk_real_account():
    connector = FutuConnector(
        {
            "acc_id": 123,
            "trade_context_factory": lambda **kwargs: FakeFutuAPI(
                accounts=[
                    {
                        "acc_id": 123,
                        "trd_env": "SIMULATE",
                        "trdmarket_auth": "HK",
                        "security_firm": "FUTUSECURITIES",
                    }
                ],
                orders=[],
                fee_rows=[],
            ),
        }
    )

    with pytest.raises(ValueError, match="Hong Kong real account"):
        connector.fetch_trade_records()


def test_futu_connector_normalizes_order_and_fee_rows():
    connector = FutuConnector(
        {
            "acc_id": 101,
            "trade_context_factory": lambda **kwargs: FakeFutuAPI(
                accounts=[
                    {
                        "acc_id": 101,
                        "trd_env": "REAL",
                        "trdmarket_auth": "HK",
                        "security_firm": "FUTUSECURITIES",
                    }
                ],
                orders=[
                    {
                        "order_id": "900000000123456789",
                        "code": "HK.00700",
                        "stock_name": "腾讯控股",
                        "trd_side": "BUY",
                        "dealt_qty": 100,
                        "dealt_avg_price": 320.5,
                        "updated_time": "2026-05-12 14:23:58",
                    }
                ],
                fee_rows=[
                    {
                        "order_id": "900000000123456789",
                        "fee_amount": 157.70,
                        "fee_details": [
                            {"fee_name": "Commission", "fee_amount": 30.00},
                            {"fee_name": "Stamp Duty", "fee_amount": 100.00},
                            {"fee_name": "Platform Fee", "fee_amount": 15.00},
                            {"fee_name": "Trading Fee", "fee_amount": 5.65},
                            {"fee_name": "SFC Transaction Levy", "fee_amount": 2.70},
                            {"fee_name": "AFRC Transaction Levy", "fee_amount": 0.15},
                            {"fee_name": "Settlement Fee", "fee_amount": 4.20},
                        ],
                    }
                ],
            ),
        }
    )

    records = connector.fetch_trade_records()

    assert len(records) == 1
    record = records[0]
    assert record["stock_code"] == "00700"
    assert record["stock_name"] == "腾讯控股"
    assert record["market"] == TradeRecord.Market.HK_STOCK
    assert record["direction"] == TradeRecord.Direction.BUY
    assert record["price"] == Decimal("320.5")
    assert record["quantity"] == 100
    assert record["source"] == TradeRecord.Source.FUTU_API
    assert record["external_trade_id"] == "900000000123456789"
    assert record["commission"] == Decimal("30.00")
    assert record["stamp_duty"] == Decimal("100.00")
    assert record["other_fees"] == Decimal("27.70")
    assert record["fee_details"][0]["fee_name"] == "Commission"


def test_futu_connector_rolls_unknown_fee_items_into_other_fees():
    connector = FutuConnector(
        {
            "acc_id": 101,
            "trade_context_factory": lambda **kwargs: FakeFutuAPI(
                accounts=[
                    {
                        "acc_id": 101,
                        "trd_env": "REAL",
                        "trdmarket_auth": "HK",
                        "security_firm": "FUTUSECURITIES",
                    }
                ],
                orders=[
                    {
                        "order_id": "900000000123456790",
                        "code": "HK.00388",
                        "stock_name": "香港交易所",
                        "trd_side": "SELL",
                        "dealt_qty": 200,
                        "dealt_avg_price": 299.8,
                        "updated_time": "2026-05-12 15:01:00",
                    }
                ],
                fee_rows=[
                    {
                        "order_id": "900000000123456790",
                        "fee_amount": 64.99,
                        "fee_details": [
                            {"fee_name": "Commission", "fee_amount": 35.00},
                            {"fee_name": "Mystery Fee", "fee_amount": 9.99},
                            {"fee_name": "Stamp Duty", "fee_amount": 20.00},
                        ],
                    }
                ],
            ),
        }
    )

    record = connector.fetch_trade_records()[0]
    assert record["commission"] == Decimal("35.00")
    assert record["stamp_duty"] == Decimal("20.00")
    assert record["other_fees"] == Decimal("9.99")


def test_futu_connector_batches_fee_queries_by_400_ids():
    orders = [
        {
            "order_id": str(900000000123450000 + index),
            "code": "HK.00700",
            "stock_name": "腾讯控股",
            "trd_side": "BUY",
            "dealt_qty": 100,
            "dealt_avg_price": 320.5,
            "updated_time": "2026-05-12 14:23:58",
        }
        for index in range(401)
    ]
    fee_rows = [
        {
            "order_id": item["order_id"],
            "fee_amount": 0,
            "fee_details": [],
        }
        for item in orders
    ]
    fake_api = FakeFutuAPI(
        accounts=[
            {
                "acc_id": 101,
                "trd_env": "REAL",
                "trdmarket_auth": "HK",
                "security_firm": "FUTUSECURITIES",
            }
        ],
        orders=orders,
        fee_rows=fee_rows,
    )
    connector = FutuConnector(
        {
            "acc_id": 101,
            "trade_context_factory": lambda **kwargs: fake_api,
        }
    )

    connector.fetch_trade_records()

    assert len(fake_api.fee_query_batches) == 2
    assert len(fake_api.fee_query_batches[0]) == 400
    assert len(fake_api.fee_query_batches[1]) == 1
