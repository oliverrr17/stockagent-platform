from decimal import Decimal

import pytest
from django.utils import timezone

from trades.models import TradeRecord
from trades.services.trade_recorder import TradeRecorder


@pytest.mark.django_db
def test_record_trade_is_idempotent_for_duplicate_payload():
    recorder = TradeRecorder()
    payload = {
        "stock_code": "00700",
        "stock_name": "Tencent",
        "market": TradeRecord.Market.HK_STOCK,
        "direction": TradeRecord.Direction.BUY,
        "price": Decimal("320.5000"),
        "quantity": 100,
        "trade_time": timezone.now(),
        "source": TradeRecord.Source.HSBC_EMAIL,
        "commission": Decimal("10.0000"),
        "stamp_duty": Decimal("2.0000"),
        "other_fees": Decimal("1.0000"),
    }

    first_record, first_created = recorder.record_trade(payload)
    second_record, second_created = recorder.record_trade(payload)

    assert first_created is True
    assert second_created is False
    assert first_record.pk == second_record.pk
    assert TradeRecord.objects.count() == 1


@pytest.mark.django_db
def test_get_trades_filters_by_supported_fields():
    now = timezone.now()
    TradeRecord.objects.create(
        stock_code="600519",
        stock_name="Kweichow Moutai",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("1500.0000"),
        quantity=10,
        trade_time=now,
        source=TradeRecord.Source.THS,
    )
    TradeRecord.objects.create(
        stock_code="00700",
        stock_name="Tencent",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.SELL,
        price=Decimal("320.5000"),
        quantity=100,
        trade_time=now,
        source=TradeRecord.Source.HSBC_EMAIL,
    )

    queryset = TradeRecorder.get_trades({"market": TradeRecord.Market.HK_STOCK})
    assert queryset.count() == 1
    assert queryset.first().stock_code == "00700"


@pytest.mark.django_db
def test_record_trade_rejects_hsbc_trade_before_ingestion_baseline():
    recorder = TradeRecorder()

    with pytest.raises(ValueError, match="ingestion baseline"):
        recorder.record_trade(
            {
                "stock_code": "00700",
                "stock_name": "Tencent",
                "market": TradeRecord.Market.HK_STOCK,
                "direction": TradeRecord.Direction.BUY,
                "price": Decimal("320.5000"),
                "quantity": 100,
                "trade_time": "2026-04-22T14:23:58+08:00",
                "source": TradeRecord.Source.HSBC_EMAIL,
                "commission": Decimal("10.0000"),
                "stamp_duty": Decimal("2.0000"),
                "other_fees": Decimal("1.0000"),
            }
        )


@pytest.mark.django_db
def test_record_trade_is_idempotent_for_futu_external_trade_id():
    recorder = TradeRecorder()
    payload = {
        "stock_code": "00700",
        "stock_name": "Tencent",
        "market": TradeRecord.Market.HK_STOCK,
        "direction": TradeRecord.Direction.BUY,
        "price": Decimal("320.5000"),
        "quantity": 100,
        "trade_time": "2026-05-12T14:23:58+08:00",
        "source": TradeRecord.Source.FUTU_API,
        "external_trade_id": "900000000123456789",
        "commission": Decimal("30.0000"),
        "stamp_duty": Decimal("100.0000"),
        "other_fees": Decimal("27.7000"),
        "fee_details": [{"fee_name": "Commission", "fee_amount": "30.00"}],
    }

    first_record, first_created = recorder.record_trade(payload)
    second_record, second_created = recorder.record_trade(payload)

    assert first_created is True
    assert second_created is False
    assert first_record.pk == second_record.pk
    assert TradeRecord.objects.filter(source=TradeRecord.Source.FUTU_API).count() == 1


@pytest.mark.django_db
def test_record_trade_persists_futu_fee_details():
    recorder = TradeRecorder()

    record, created = recorder.record_trade(
        {
            "stock_code": "00388",
            "stock_name": "HKEX",
            "market": TradeRecord.Market.HK_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": Decimal("299.8000"),
            "quantity": 200,
            "trade_time": "2026-05-12T15:01:00+08:00",
            "source": TradeRecord.Source.FUTU_API,
            "external_trade_id": "900000000123456790",
            "commission": Decimal("35.0000"),
            "stamp_duty": Decimal("60.0000"),
            "other_fees": Decimal("18.2200"),
            "fee_details": [
                {"fee_name": "Commission", "fee_amount": "35.00"},
                {"fee_name": "Stamp Duty", "fee_amount": "60.00"},
                {"fee_name": "Trading Fee", "fee_amount": "3.39"},
            ],
        }
    )

    assert created is True
    assert record.external_trade_id == "900000000123456790"
    assert record.fee_details[0]["fee_name"] == "Commission"
