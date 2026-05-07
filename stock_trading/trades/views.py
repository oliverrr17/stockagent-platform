from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import TradeRecord
from .serializers import TradeRecordSerializer
from .services.trade_recorder import TradeRecorder


class TradeRecordViewSet(viewsets.ModelViewSet):
    queryset = TradeRecord.objects.all()
    serializer_class = TradeRecordSerializer
    filterset_fields = ["market", "direction", "stock_code"]
    ordering_fields = ["trade_time", "created_at"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            trade, created = TradeRecorder().record_trade(serializer.validated_data)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        response_serializer = self.get_serializer(trade)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        for field in ("market", "direction", "stock_code"):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        ordering = params.get("ordering")
        if ordering:
            requested_fields = [item.strip() for item in ordering.split(",") if item.strip()]
            allowed = set(self.ordering_fields)
            normalized = [item.lstrip("-") for item in requested_fields]
            if all(item in allowed for item in normalized):
                queryset = queryset.order_by(*requested_fields)

        return queryset
