from django.db.models import Q
from rest_framework import viewsets

from .models import NewsItem, NotificationLog
from .serializers import NewsItemSerializer, NotificationLogSerializer


class NewsItemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NewsItem.objects.all()
    serializer_class = NewsItemSerializer
    filterset_fields = ["stock_code", "category", "source", "pushed"]
    ordering_fields = ["published_at", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        for field in ("stock_code", "category", "source"):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        pushed = params.get("pushed")
        if pushed is not None and pushed != "":
            queryset = queryset.filter(pushed=str(pushed).lower() == "true")

        query = params.get("query")
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(summary__icontains=query))

        ordering = params.get("ordering")
        if ordering:
            requested_fields = [item.strip() for item in ordering.split(",") if item.strip()]
            allowed = set(self.ordering_fields)
            normalized = [item.lstrip("-") for item in requested_fields]
            if all(item in allowed for item in normalized):
                queryset = queryset.order_by(*requested_fields)

        return queryset


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotificationLog.objects.select_related("news_item").all()
    serializer_class = NotificationLogSerializer
    filterset_fields = ["status", "channel", "news_item"]
    ordering_fields = ["sent_at", "id"]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        for field in ("status", "channel", "news_item"):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        stock_code = params.get("stock_code")
        if stock_code:
            queryset = queryset.filter(news_item__stock_code=stock_code)

        ordering = params.get("ordering")
        if ordering:
            requested_fields = [item.strip() for item in ordering.split(",") if item.strip()]
            allowed = set(self.ordering_fields)
            normalized = [item.lstrip("-") for item in requested_fields]
            if all(item in allowed for item in normalized):
                queryset = queryset.order_by(*requested_fields)

        return queryset
