from django.db import models

from trades.models import TradeRecord


class ReviewReport(models.Model):
    trade_record = models.ForeignKey(TradeRecord, on_delete=models.CASCADE, related_name="review_reports")
    report_kind = models.CharField(max_length=20, default="llm_coach")
    engine_version = models.CharField(max_length=50, default="llm_review_v1")
    version = models.PositiveIntegerField(default=1)
    is_latest = models.BooleanField(default=True)
    volume_analysis = models.JSONField(default=dict, blank=True)
    chip_analysis = models.JSONField(default=dict, blank=True)
    trend_analysis = models.JSONField(default=dict, blank=True)
    intent_snapshot = models.JSONField(default=dict, blank=True)
    objective_summary = models.JSONField(default=dict, blank=True)
    intent_gap_diagnosis = models.JSONField(default=dict, blank=True)
    subscores = models.JSONField(default=dict, blank=True)
    coach_report_payload = models.JSONField(default=dict, blank=True)
    evidence_payload = models.JSONField(default=dict, blank=True)
    overall_score = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        unique_together = ["trade_record", "version"]
