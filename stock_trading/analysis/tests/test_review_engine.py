from decimal import Decimal

import pytest
from django.utils import timezone

from analysis.models import ReviewReport
from analysis.services.review_engine import ReviewEngine
from trades.models import TradeRecord


class StaticAnalyzer:
    def __init__(self, payload):
        self.payload = payload

    def analyze(self, trade):
        return dict(self.payload)


class StaticBuilder:
    def __init__(self, payload):
        self.payload = payload

    def build(self, trade):
        return dict(self.payload)


class StaticLLMService:
    def review(self, evidence):
        return {
            "overall_score": 78,
            "subscores": {
                "decision_quality": 24,
                "context_alignment": 16,
                "execution_quality": 15,
                "risk_discipline": 15,
                "emotion_discipline": 8,
            },
            "objective_summary": {
                "market_heat": "risk_on",
                "industry_heat": "hot",
                "company_quality": "solid",
            },
            "intent_gap_diagnosis": {
                "gap_level": "medium",
                "gap_items": ["主观判断偏乐观"],
            },
            "coach_report_payload": {
                "user_intent_summary": "想做趋势跟随突破。",
                "objective_context_summary": "市场偏强，行业偏热。",
                "overall_verdict": "这笔交易基本符合系统，但位置略激进。",
                "setup_review": "突破条件基本成立。",
                "execution_review": "入场略早，但仍在可接受范围。",
                "risk_plan_review": "止损和止盈计划完整。",
                "exit_review": "",
                "pnl_attribution": "盈亏主要取决于入场位置和行业强度。",
                "pattern_tag": "trend_breakout",
                "follow_up_advice": "若仍持仓，观察行业热度是否持续。",
                "next_time_rules": ["下次突破需确认放量。"],
                "missing_data_notes": [],
            },
        }


@pytest.mark.django_db
def test_review_engine_generates_versioned_llm_report():
    trade = TradeRecord.objects.create(
        stock_code="603063",
        stock_name="Hopesun",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("41.4300"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.THS,
    )

    engine = ReviewEngine(
        volume=StaticAnalyzer({"volume_signal": "high", "volume_chart": []}),
        chip=StaticAnalyzer({"position_zone": "mid_zone"}),
        trend=StaticAnalyzer({"trend_phase": "breakout_attempt", "price_chart": []}),
        market_heat_builder=StaticBuilder({"market_heat": "risk_on"}),
        industry_heat_builder=StaticBuilder({"industry_heat": "hot"}),
        company_quality_builder=StaticBuilder({"company_quality": "solid"}),
        llm_service=StaticLLMService(),
    )

    first = engine.generate_report(trade)
    second = engine.generate_report(trade)

    assert ReviewReport.objects.filter(trade_record=trade).count() == 2
    assert second.version == 2
    assert second.is_latest is True
    assert first.version == 1
    first.refresh_from_db()
    assert first.is_latest is False
    assert second.overall_score == 78
    assert second.subscores["decision_quality"] == 24
    assert second.coach_report_payload["follow_up_advice"]
    assert second.coach_report_payload["next_time_rules"] == ["下次突破需确认放量。"]
    assert second.intent_gap_diagnosis["gap_level"] == "medium"


@pytest.mark.django_db
def test_review_engine_embeds_intent_snapshot_when_present():
    trade = TradeRecord.objects.create(
        stock_code="600519",
        stock_name="贵州茅台",
        market=TradeRecord.Market.A_STOCK,
        direction=TradeRecord.Direction.BUY,
        price=Decimal("1403.2000"),
        quantity=100,
        trade_time=timezone.now(),
        source=TradeRecord.Source.MANUAL,
    )
    trade.__dict__["intent_snapshot"] = type(
        "IntentSnapshotStub",
        (),
        {
            "setup_tags": ["breakout"],
            "market_context_tags": ["market_strong"],
            "security_quality_tags": ["leader"],
            "execution_emotion_tags": ["calm"],
            "overall_notes": "放量突破，市场偏强，标的是龙头，执行较冷静。",
            "planned_holding_period": "swing",
            "planned_stop_loss_type": "fixed_price",
            "planned_stop_loss_value": Decimal("1360.0000"),
            "planned_take_profit_type": "prior_high",
            "planned_take_profit_value": Decimal("1480.0000"),
        },
    )()

    engine = ReviewEngine(
        volume=StaticAnalyzer({"volume_signal": "high", "volume_chart": []}),
        chip=StaticAnalyzer({"position_zone": "mid_zone"}),
        trend=StaticAnalyzer({"trend_phase": "breakout_attempt", "price_chart": []}),
        market_heat_builder=StaticBuilder({"market_heat": "risk_on"}),
        industry_heat_builder=StaticBuilder({"industry_heat": "hot"}),
        company_quality_builder=StaticBuilder({"company_quality": "solid"}),
        llm_service=StaticLLMService(),
    )

    report = engine.generate_report(trade)

    assert report.intent_snapshot["setup_tags"] == ["breakout"]
    assert report.intent_snapshot["overall_notes"] == "放量突破，市场偏强，标的是龙头，执行较冷静。"
    assert report.intent_snapshot["planned_holding_period"] == "swing"
    assert report.coach_report_payload["user_intent_summary"] == "想做趋势跟随突破。"
