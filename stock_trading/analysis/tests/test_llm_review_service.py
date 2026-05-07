from analysis.services.llm_review_service import LLMReviewService


def test_deepseek_v4_payload_disables_thinking_by_default():
    service = LLMReviewService()
    service.model = "deepseek-v4-flash"

    payload = service._build_request_payload({"hello": "world"})

    assert payload["model"] == "deepseek-v4-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in payload


def test_non_deepseek_payload_keeps_generic_shape():
    service = LLMReviewService()
    service.model = "gpt-4o-mini"

    payload = service._build_request_payload({"hello": "world"})

    assert payload["model"] == "gpt-4o-mini"
    assert payload["response_format"] == {"type": "json_object"}
    assert "extra_body" not in payload


def test_normalize_payload_keeps_missing_data_notes_as_full_strings():
    service = LLMReviewService()
    payload = service._normalize_payload(
        {
            "overall_score": 60,
            "subscores": {
                "decision_quality": 20,
                "context_alignment": 10,
                "execution_quality": 10,
                "risk_discipline": 10,
                "emotion_discipline": 5,
            },
            "objective_summary": {},
            "intent_gap_diagnosis": {},
            "coach_report_payload": {
                "missing_data_notes": "intent_snapshot 因用户未填写而 degraded",
                "next_time_rules": ["补充计划"],
            },
        },
        {
            "market_heat": {"risk_preference": "unknown"},
            "industry_heat": {"heat_level": "unknown"},
            "company_quality": {"profitability": "unknown"},
        },
        "",
    )

    assert payload["coach_report_payload"]["missing_data_notes"] == [
        "intent_snapshot 因用户未填写而 degraded"
    ]
