from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import transaction
from django.utils import timezone

from analysis.services.market_data import build_market_data_provider
from .models import CashAccount, CashFlow, Position, PositionEntry
from .serializers import (
    CashAccountSerializer,
    CashFlowSerializer,
    ClearedPositionSerializer,
    HKStockStatsSerializer,
    PortfolioDailyContributionResponseSerializer,
    PortfolioOverviewSerializer,
    PositionAnalyticsSerializer,
    PositionSerializer,
)
from .services.portfolio_analytics import PortfolioAnalyticsService
from .services.cost_calculator import CostCalculator
from .services.portfolio_manager import PortfolioManager
from trades.serializers import TradeRecordSerializer


class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.all()
    serializer_class = PositionSerializer

    @action(detail=False, methods=["get"])
    def active(self, request):
        queryset = self.get_queryset().filter(status=Position.Status.ACTIVE, quantity__gt=0)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def manual_entry(self, request):
        try:
            position = PortfolioManager().add_position(request.data)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        serializer = self.get_serializer(position)
        return Response(serializer.data, status=201)

    def partial_update(self, request, *args, **kwargs):
        position = self.get_object()
        payload = {
            "stock_code": request.data.get("stock_code", position.stock_code),
            "stock_name": request.data.get("stock_name", position.stock_name),
            "market": request.data.get("market", position.market),
            "quantity": request.data.get("quantity", position.quantity),
            "cost_price": request.data.get("cost_price", position.weighted_avg_cost),
        }
        try:
            updated = PortfolioManager().update_position(position.id, payload)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        serializer = self.get_serializer(updated)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        position = self.get_object()
        entry_queryset = PositionEntry.objects.filter(stock_code=position.stock_code, market=position.market)
        if not entry_queryset.exists():
            raise ValidationError({"detail": "Only manually initialized positions can be deleted from the UI."})

        with transaction.atomic():
            entry_queryset.delete()
            position.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class HKStockStatsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Position.objects.none()
    serializer_class = HKStockStatsSerializer

    def retrieve(self, request, *args, **kwargs):
        stock_code = kwargs.get("pk")
        try:
            stats = CostCalculator(build_market_data_provider()).get_hk_stock_stats(stock_code)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        serializer = self.get_serializer(stats)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def trade_history(self, request, pk=None):
        queryset = CostCalculator().get_trade_history(pk)
        serializer = TradeRecordSerializer(queryset, many=True)
        return Response(serializer.data)


class CashAccountViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CashAccount.objects.prefetch_related("flows").all()
    serializer_class = CashAccountSerializer


class CashFlowViewSet(viewsets.ModelViewSet):
    queryset = CashFlow.objects.select_related("cash_account").all()
    serializer_class = CashFlowSerializer

    def create(self, request, *args, **kwargs):
        currency = request.data.get("currency")
        if currency not in {CashAccount.Currency.CNY, CashAccount.Currency.HKD}:
            raise ValidationError({"detail": "currency must be CNY or HKD"})

        account, _ = CashAccount.objects.get_or_create(currency=currency, defaults={"label": currency})
        serializer = self.get_serializer(
            data={
                "cash_account": account.id,
                "direction": request.data.get("direction"),
                "amount": request.data.get("amount"),
                "occurred_at": request.data.get("occurred_at"),
                "note": request.data.get("note", ""),
            }
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PortfolioOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analytics = PortfolioAnalyticsService(build_market_data_provider()).get_overview()
        serializer = PortfolioOverviewSerializer(analytics)
        return Response(serializer.data)


class PortfolioDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        provider = build_market_data_provider()
        service = PortfolioAnalyticsService(provider)
        active_positions = Position.objects.filter(status=Position.Status.ACTIVE, quantity__gt=0)
        position_rows = service.get_position_analytics()
        effective_end = service._effective_end_date()
        overview = service.get_overview(
            active_rows=position_rows,
            cash_balances=service.get_cash_balances(effective_end),
        )
        return Response(
            {
                "positions": PositionSerializer(active_positions, many=True).data,
                "position_analytics": PositionAnalyticsSerializer(position_rows, many=True).data,
                "overview": PortfolioOverviewSerializer(overview).data,
                "cash_accounts": CashAccountSerializer(CashAccount.objects.prefetch_related("flows").all(), many=True).data,
                "cash_flows": CashFlowSerializer(
                    CashFlow.objects.select_related("cash_account").all().order_by("-occurred_at", "-id"),
                    many=True,
                ).data,
            }
        )


class PortfolioPositionAnalyticsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = PortfolioAnalyticsService(build_market_data_provider()).get_position_analytics()
        serializer = PositionAnalyticsSerializer(rows, many=True)
        return Response(serializer.data)


class PortfolioPositionAnalyticsDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, stock_code: str):
        try:
            row = PortfolioAnalyticsService(build_market_data_provider()).get_position_detail(stock_code)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        serializer = PositionAnalyticsSerializer(row)
        return Response(serializer.data)


class ClearedPositionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = PortfolioAnalyticsService(build_market_data_provider()).get_cleared_positions()
        serializer = ClearedPositionSerializer(rows, many=True)
        return Response(serializer.data)


class PortfolioDailyContributionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, snapshot_date: str):
        payload = PortfolioAnalyticsService(build_market_data_provider()).get_daily_contributions(
            timezone.datetime.fromisoformat(snapshot_date).date()
        )
        serializer = PortfolioDailyContributionResponseSerializer(payload)
        return Response(serializer.data)
