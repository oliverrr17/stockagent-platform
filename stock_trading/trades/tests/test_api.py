from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from trades.models import TradeRecord


@pytest.fixture
def api_client(db):
    user = get_user_model().objects.create_user(username="trades-api", password="secret")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_trade_record_create_and_filter(api_client):
    response = api_client.post(
        "/api/trades/",
        {
            "stock_code": "603063",
            "stock_name": "禾望电气",
            "market": TradeRecord.Market.A_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": "41.4300",
            "quantity": 100,
            "trade_time": timezone.now().isoformat(),
            "source": TradeRecord.Source.THS,
            "commission": "0",
            "stamp_duty": "0",
            "other_fees": "0",
        },
        format="json",
    )

    assert response.status_code == 201
    list_response = api_client.get("/api/trades/?stock_code=603063")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["stock_code"] == "603063"


@pytest.mark.django_db
def test_trade_record_create_accepts_intent_snapshot(api_client):
    response = api_client.post(
        "/api/trades/",
        {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "market": TradeRecord.Market.A_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": "1403.2000",
            "quantity": 100,
            "trade_time": "2026-04-24T14:00:00+08:00",
            "source": TradeRecord.Source.MANUAL,
            "commission": "0",
            "stamp_duty": "0",
            "other_fees": "0",
            "intent_snapshot": {
                "setup_tags": ["breakout", "trend_follow"],
                "market_context_tags": ["market_strong", "sector_hot"],
                "security_quality_tags": ["leader", "quality_compounder"],
                "execution_emotion_tags": ["disciplined", "calm"],
                "overall_notes": "放量突破后跟随，白酒板块相对强势，核心资产，严格按计划执行。",
                "planned_holding_period": "swing",
                "planned_stop_loss_type": "structure_low",
                "planned_stop_loss_value": "1360.0000",
                "planned_take_profit_type": "prior_high",
                "planned_take_profit_value": "1480.0000",
            },
        },
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["intent_snapshot"]["setup_tags"] == ["breakout", "trend_follow"]
    assert payload["intent_snapshot"]["overall_notes"] == "放量突破后跟随，白酒板块相对强势，核心资产，严格按计划执行。"
    assert payload["intent_snapshot"]["planned_holding_period"] == "swing"
    assert payload["intent_snapshot"]["planned_stop_loss_value"] == "1360.0000"


@pytest.mark.django_db
def test_trade_record_create_with_manual_source_updates_position(api_client):
    response = api_client.post(
        "/api/trades/",
        {
            "stock_code": "603063",
            "stock_name": "测试公司",
            "market": TradeRecord.Market.A_STOCK,
            "direction": TradeRecord.Direction.BUY,
            "price": "40.2800",
            "quantity": 200,
            "trade_time": "2026-04-24T14:00:00+08:00",
            "source": TradeRecord.Source.MANUAL,
            "commission": "0",
            "stamp_duty": "0",
            "other_fees": "0",
        },
        format="json",
    )

    assert response.status_code == 201

    from portfolio.models import Position

    position = Position.objects.get(stock_code="603063", market=TradeRecord.Market.A_STOCK)
    assert position.quantity == 200
    assert position.weighted_avg_cost == Decimal("40.2800")


@pytest.mark.django_db
def test_trade_record_patch_updates_intent_snapshot(api_client):
    trade = TradeRecord.objects.create(
        stock_code="600519",
        stock_name="贵州茅台",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("1403.2000"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.MANUAL,
        commission=Decimal("0"),
        stamp_duty=Decimal("0"),
        other_fees=Decimal("0"),
    )

    response = api_client.patch(
        f"/api/trades/{trade.id}/",
        {
            "intent_snapshot": {
                "setup_tags": ["pullback"],
                "market_context_tags": ["market_neutral"],
                "security_quality_tags": ["quality_compounder"],
                "execution_emotion_tags": ["hesitant"],
                "overall_notes": "回踩后低吸，入场略犹豫。",
                "planned_holding_period": "position",
                "planned_stop_loss_type": "fixed_price",
                "planned_stop_loss_value": "1388.0000",
                "planned_take_profit_type": "rr_multiple",
                "planned_take_profit_value": "1449.0000",
            }
        },
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent_snapshot"]["setup_tags"] == ["pullback"]
    assert payload["intent_snapshot"]["execution_emotion_tags"] == ["hesitant"]
    assert payload["intent_snapshot"]["overall_notes"] == "回踩后低吸，入场略犹豫。"
    assert payload["intent_snapshot"]["planned_take_profit_type"] == "rr_multiple"


@pytest.mark.django_db
def test_trade_record_list_respects_ordering(api_client):
    older = timezone.now() - timezone.timedelta(hours=1)
    newer = timezone.now()
    TradeRecord.objects.create(
        stock_code="603063",
        stock_name="禾望电气",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("41.4300"),
        quantity=100,
        trade_time=older,
        source=TradeRecord.Source.THS,
    )
    TradeRecord.objects.create(
        stock_code="02610",
        stock_name="南山铝业国际",
        market=TradeRecord.Market.HK_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("58.5000"),
        quantity=100,
        trade_time=newer,
        source=TradeRecord.Source.HSBC_EMAIL,
    )

    response = api_client.get("/api/trades/?ordering=trade_time")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["stock_code"] == "603063"
    assert payload[1]["stock_code"] == "02610"
