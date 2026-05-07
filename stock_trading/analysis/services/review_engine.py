from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from analysis.models import ReviewReport

from .company_quality_builder import CompanyQualitySnapshotBuilder
from .industry_heat_builder import IndustryHeatSnapshotBuilder
from .llm_review_service import LLMReviewService
from .market_heat_builder import MarketHeatSnapshotBuilder
from .review_evidence_builder import ReviewEvidenceBuilder
from .tushare_support import TushareProAdapter


class ReviewEngine:
    ENGINE_VERSION = "llm_review_v1"
    REPORT_KIND = "llm_coach"

    def __init__(
        self,
        volume,
        chip,
        trend,
        *,
        market_heat_builder=None,
        industry_heat_builder=None,
        company_quality_builder=None,
        llm_service=None,
        evidence_builder=None,
        market_api=None,
        tushare_client=None,
    ):
        self.volume = volume
        self.chip = chip
        self.trend = trend
        self.market_api = market_api
        self.tushare_client = tushare_client or TushareProAdapter()
        self.market_heat_builder = market_heat_builder or MarketHeatSnapshotBuilder(
            tushare_client=self.tushare_client,
        )
        self.industry_heat_builder = industry_heat_builder or IndustryHeatSnapshotBuilder(
            tushare_client=self.tushare_client,
            market_api=market_api,
        )
        self.company_quality_builder = company_quality_builder or CompanyQualitySnapshotBuilder(
            tushare_client=self.tushare_client,
        )
        self.llm_service = llm_service or LLMReviewService()
        self.evidence_builder = evidence_builder or ReviewEvidenceBuilder(market_api=market_api)

    def generate_report(self, trade):
        volume_result = self.volume.analyze(trade)
        chip_result = self.chip.analyze(trade)
        trend_result = self.trend.analyze(trade)
        market_heat = self.market_heat_builder.build(trade)
        industry_heat = self.industry_heat_builder.build(trade)
        company_quality = self.company_quality_builder.build(trade)
        evidence = self.evidence_builder.build(
            trade,
            volume_analysis=volume_result,
            chip_analysis=chip_result,
            trend_analysis=trend_result,
            market_heat=market_heat,
            industry_heat=industry_heat,
            company_quality=company_quality,
        )
        review_payload = self.llm_service.review(evidence)

        with transaction.atomic():
            ReviewReport.objects.filter(trade_record=trade, is_latest=True).update(is_latest=False)
            latest_version = (
                ReviewReport.objects.filter(trade_record=trade).aggregate(max_version=Max("version"))["max_version"]
                or 0
            )
            report = ReviewReport.objects.create(
                trade_record=trade,
                report_kind=self.REPORT_KIND,
                engine_version=self.ENGINE_VERSION,
                version=latest_version + 1,
                is_latest=True,
                volume_analysis=volume_result,
                chip_analysis=chip_result,
                trend_analysis=trend_result,
                intent_snapshot=evidence["intent_snapshot"],
                objective_summary=review_payload.get("objective_summary", {}),
                intent_gap_diagnosis=review_payload.get("intent_gap_diagnosis", {}),
                subscores=review_payload.get("subscores", {}),
                coach_report_payload=review_payload.get("coach_report_payload", {}),
                evidence_payload=evidence,
                overall_score=int(review_payload.get("overall_score", 0)),
            )
        return report
