from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import ReviewReport
from .serializers import ReviewReportSerializer
from .services.chip_analyzer import ChipAnalyzer
from .services.market_data import build_market_data_provider
from .services.review_engine import ReviewEngine
from .services.trend_analyzer import TrendAnalyzer
from .services.volume_analyzer import VolumeAnalyzer
from trades.models import TradeRecord


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = ReviewReport.objects.all()
    serializer_class = ReviewReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related("trade_record").order_by("-is_latest", "-created_at", "-id")
        trade_record_id = self.request.query_params.get("trade_record")
        if trade_record_id:
            queryset = queryset.filter(trade_record_id=trade_record_id)
        return queryset

    @action(detail=False, methods=["post"])
    def generate(self, request):
        trade_record_id = request.data.get("trade_record_id") or request.data.get("trade_record")
        if not trade_record_id:
            raise ValidationError({"detail": "trade_record_id is required."})

        try:
            trade = TradeRecord.objects.get(pk=trade_record_id)
        except TradeRecord.DoesNotExist as exc:
            raise ValidationError({"detail": "TradeRecord not found."}) from exc

        market_data_provider = build_market_data_provider()
        engine = ReviewEngine(
            volume=VolumeAnalyzer(market_api=market_data_provider),
            chip=ChipAnalyzer(market_api=market_data_provider),
            trend=TrendAnalyzer(market_api=market_data_provider),
            market_api=market_data_provider,
        )
        report = engine.generate_report(trade)
        serializer = self.get_serializer(report)
        return Response(serializer.data, status=201)
