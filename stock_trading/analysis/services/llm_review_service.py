from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from trades.models import TradeRecord


_TAG_LABELS = {
    "breakout": "突破",
    "trend_follow": "趋势跟随",
    "pullback": "回踩",
    "rebound": "反弹",
    "low_absorption": "低吸",
    "stop_loss_exit": "止损离场",
    "profit_take": "止盈兑现",
    "reduce_position": "减仓",
    "market_strong": "市场偏强",
    "market_neutral": "市场中性",
    "market_weak": "市场偏弱",
    "sector_hot": "行业偏热",
    "sector_neutral": "行业中性",
    "sector_cold": "行业偏冷",
    "rotation_trade": "轮动博弈",
    "leader": "龙头",
    "follower": "跟风",
    "quality_compounder": "高质量公司",
    "event_driven": "事件驱动",
    "sentiment_driven": "情绪驱动",
    "cyclical": "周期属性",
    "disciplined": "执行纪律好",
    "calm": "情绪稳定",
    "hesitant": "执行犹豫",
    "fomo": "FOMO",
    "fear_of_drawdown": "怕回撤",
    "revenge_trade": "报复交易",
    "chasing": "追高",
    "early_profit_taking": "过早兑现",
}


class LLMReviewService:
    SYSTEM_PROMPT = """你是一名严格的交易复盘教练。请只基于给定的本地证据做判断，不要联网，不要编造。

用户填写的 intent_snapshot 只是主观先验，不代表事实。你必须先基于 objective evidence 形成自己的结论，再诊断主观与客观的偏差。

请严格输出 JSON，对应字段：
- overall_score: 0-100 整数
- subscores: {decision_quality, context_alignment, execution_quality, risk_discipline, emotion_discipline}
- objective_summary: {market_heat, industry_heat, company_quality}
- intent_gap_diagnosis: {gap_level, gap_items}
- coach_report_payload: {
  user_intent_summary,
  objective_context_summary,
  overall_verdict,
  setup_review,
  execution_review,
  risk_plan_review,
  exit_review,
  pnl_attribution,
  pattern_tag,
  follow_up_advice,
  next_time_rules,
  missing_data_notes
}

评分规则：
- 盈利本身不直接加分，违背计划、环境误判、情绪化交易才扣分。
- 允许“做对但亏钱”和“做错但赚钱”。
- next_time_rules 必须是 3-5 条可执行中文规则。
"""

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.base_url = (os.getenv("REVIEW_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()
        self.api_key = (os.getenv("REVIEW_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        self.model = (os.getenv("REVIEW_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def review(self, evidence: dict) -> dict:
        if not self.is_configured():
            return self._fallback_report(evidence, "review_llm_not_configured")

        try:
            return self._review_with_remote_model(evidence)
        except Exception as exc:
            return self._fallback_report(evidence, f"review_llm_error:{exc.__class__.__name__}")

    def _review_with_remote_model(self, evidence: dict) -> dict:
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        payload = self._build_request_payload(evidence)
        response = self.session.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return self._normalize_payload(self._parse_json_content(content), evidence, "")

    def _build_request_payload(self, evidence: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        if self._should_disable_thinking():
            payload["extra_body"] = {"thinking": {"type": "disabled"}}
        return payload

    def _should_disable_thinking(self) -> bool:
        model = (self.model or "").strip().lower()
        return model.startswith("deepseek-v4")

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)

    def _fallback_report(self, evidence: dict, missing_reason: str) -> dict:
        trade = evidence["trade"]
        intent = evidence["intent_snapshot"]
        market_heat = evidence["market_heat"]
        industry_heat = evidence["industry_heat"]
        company_quality = evidence["company_quality"]
        trend = evidence["trend_analysis"]
        forward = evidence["forward_path"]

        intent_labels = self._tag_labels(intent.get("setup_tags", []))
        market_labels = self._tag_labels(intent.get("market_context_tags", []))
        security_labels = self._tag_labels(intent.get("security_quality_tags", []))
        emotion_labels = self._tag_labels(intent.get("execution_emotion_tags", []))

        if trade["direction"] == TradeRecord.Direction.BUY:
            overall_verdict = "这笔交易可复盘，但当前 LLM 不可用，先依据本地证据给出基础教练结论。"
            exit_review = ""
            follow_up_advice = "若仍持仓，优先跟踪市场和行业热度是否继续维持。"
        else:
            overall_verdict = "这笔离场交易可复盘，但当前 LLM 不可用，先依据本地证据给出基础教练结论。"
            exit_review = "离场质量需要结合卖出后 5 日表现继续评估。"
            follow_up_advice = "若已离场，重点回看卖出后 5 日走势是否验证离场合理。"

        gap_items = []
        if intent.get("market_context_tags") and market_heat.get("risk_preference") not in {"unknown", "neutral"}:
            subjective_market = ",".join(intent.get("market_context_tags", []))
            objective_market = market_heat.get("risk_preference")
            if subjective_market and objective_market and objective_market not in subjective_market:
                gap_items.append("主观市场环境判断与客观市场热度存在偏差")
        if intent.get("execution_emotion_tags") and "disciplined" in intent.get("execution_emotion_tags", []) and forward.get("max_adverse_excursion_pct") not in (None,):
            if float(forward["max_adverse_excursion_pct"]) <= -5.0:
                gap_items.append("主观执行自评偏乐观，仓位或止损执行仍需复核")

        overall_score = 68
        if market_heat.get("degraded") or industry_heat.get("degraded") or company_quality.get("degraded"):
            overall_score = 62
        if "fomo" in intent.get("execution_emotion_tags", []) or "chasing" in intent.get("execution_emotion_tags", []):
            overall_score -= 8
            gap_items.append("存在情绪化执行风险")

        payload = {
            "overall_score": max(0, min(100, overall_score)),
            "subscores": {
                "decision_quality": 20,
                "context_alignment": 13,
                "execution_quality": 14,
                "risk_discipline": 11,
                "emotion_discipline": 10 if not emotion_labels else 8,
            },
            "objective_summary": {
                "market_heat": market_heat.get("risk_preference", "unknown"),
                "industry_heat": industry_heat.get("heat_level", "unknown"),
                "company_quality": company_quality.get("profitability", "unknown"),
            },
            "intent_gap_diagnosis": {
                "gap_level": "medium" if gap_items else "low",
                "gap_items": gap_items or ["当前主观意图与客观证据没有明显硬冲突，但仍需更完整数据校验。"],
            },
            "coach_report_payload": {
                "user_intent_summary": self._build_intent_summary(
                    intent_labels,
                    market_labels,
                    security_labels,
                    emotion_labels,
                    intent,
                ),
                "objective_context_summary": (
                    f"市场热度={market_heat.get('risk_preference', 'unknown')}，"
                    f"行业热度={industry_heat.get('heat_level', 'unknown')}，"
                    f"公司质地={company_quality.get('profitability', 'unknown')}。"
                ),
                "overall_verdict": overall_verdict,
                "setup_review": f"当前趋势阶段为 {trend.get('trend_phase', 'unknown')}，需要结合 setup 标签判断入场前提是否充分。",
                "execution_review": "先看入场位置、费用与情绪标签，重点排查是否存在追高、犹豫和计划外执行。",
                "risk_plan_review": "优先核对计划止损、计划止盈和计划持有周期是否完整，缺失时不应给高分。",
                "exit_review": exit_review,
                "pnl_attribution": "先把盈亏归因为环境、位置、纪律和情绪，而不是简单归因为赚了或亏了。",
                "pattern_tag": intent_labels[0] if intent_labels else "unclassified_trade",
                "follow_up_advice": follow_up_advice,
                "next_time_rules": [
                    "下次遇到同类 setup，先确认市场热度和行业热度是否同向。",
                    "没有明确止损和止盈计划时，不要给自己高质量执行评价。",
                    "如果情绪标签包含 FOMO、追高或犹豫，下次必须等待额外确认信号。",
                ],
                "missing_data_notes": [missing_reason],
            },
        }
        return self._normalize_payload(payload, evidence, missing_reason)

    def _normalize_payload(self, payload: dict, evidence: dict, missing_reason: str) -> dict:
        coach = payload.setdefault("coach_report_payload", {})
        gap = payload.setdefault("intent_gap_diagnosis", {})
        objective = payload.setdefault("objective_summary", {})
        subscores = payload.setdefault("subscores", {})

        for key, default in (
            ("decision_quality", 0),
            ("context_alignment", 0),
            ("execution_quality", 0),
            ("risk_discipline", 0),
            ("emotion_discipline", 0),
        ):
            subscores[key] = int(max(0, min(30 if key == "decision_quality" else 20 if key != "emotion_discipline" else 10, subscores.get(key, default))))

        payload["overall_score"] = int(max(0, min(100, payload.get("overall_score", sum(subscores.values())))))
        objective.setdefault("market_heat", evidence.get("market_heat", {}).get("risk_preference", "unknown"))
        objective.setdefault("industry_heat", evidence.get("industry_heat", {}).get("heat_level", "unknown"))
        objective.setdefault("company_quality", evidence.get("company_quality", {}).get("profitability", "unknown"))
        gap.setdefault("gap_level", "low")
        gap.setdefault("gap_items", [])
        coach.setdefault("user_intent_summary", "未填写交易前意图。")
        coach.setdefault("objective_context_summary", "客观环境证据不足。")
        coach.setdefault("overall_verdict", "暂无明确结论。")
        coach.setdefault("setup_review", "")
        coach.setdefault("execution_review", "")
        coach.setdefault("risk_plan_review", "")
        coach.setdefault("exit_review", "")
        coach.setdefault("pnl_attribution", "")
        coach.setdefault("pattern_tag", "unclassified_trade")
        coach.setdefault("follow_up_advice", "后续建议不足。")
        coach.setdefault("next_time_rules", ["补充更多结构化复盘数据。"])
        notes_value = coach.get("missing_data_notes", []) or []
        if isinstance(notes_value, str):
            notes = [notes_value]
        else:
            notes = [str(item) for item in notes_value]
        if missing_reason and missing_reason not in notes:
            notes.append(missing_reason)
        coach["missing_data_notes"] = notes
        if not isinstance(coach["next_time_rules"], list):
            coach["next_time_rules"] = [str(coach["next_time_rules"])]
        return payload

    def _tag_labels(self, values):
        return [_TAG_LABELS.get(value, value) for value in values]

    def _build_intent_summary(self, intent_labels, market_labels, security_labels, emotion_labels, intent):
        fragments = []
        if intent_labels:
            fragments.append(f"交易 setup: {'、'.join(intent_labels)}")
        if market_labels:
            fragments.append(f"主观看到的市场环境: {'、'.join(market_labels)}")
        if security_labels:
            fragments.append(f"主观看到的标的属性: {'、'.join(security_labels)}")
        if emotion_labels:
            fragments.append(f"执行与情绪: {'、'.join(emotion_labels)}")
        if intent.get("overall_notes"):
            fragments.append(str(intent["overall_notes"]))
        return "；".join(fragments) if fragments else "未填写交易前意图。"
