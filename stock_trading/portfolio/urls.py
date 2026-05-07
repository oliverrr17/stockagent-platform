from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CashAccountViewSet,
    CashFlowViewSet,
    ClearedPositionListView,
    HKStockStatsViewSet,
    PortfolioDashboardView,
    PortfolioDailyContributionView,
    PortfolioOverviewView,
    PortfolioPositionAnalyticsDetailView,
    PortfolioPositionAnalyticsListView,
    PositionViewSet,
)


router = DefaultRouter()
router.register("positions", PositionViewSet, basename="position")
router.register("hk-stats", HKStockStatsViewSet, basename="hk-stock-stats")
router.register("cash-accounts", CashAccountViewSet, basename="cash-account")
router.register("cash-flows", CashFlowViewSet, basename="cash-flow")

urlpatterns = router.urls + [
    path("analytics/dashboard/", PortfolioDashboardView.as_view(), name="portfolio-dashboard"),
    path("analytics/overview/", PortfolioOverviewView.as_view(), name="portfolio-overview"),
    path(
        "analytics/contributions/<str:snapshot_date>/",
        PortfolioDailyContributionView.as_view(),
        name="portfolio-daily-contributions",
    ),
    path("analytics/positions/", PortfolioPositionAnalyticsListView.as_view(), name="portfolio-position-analytics-list"),
    path(
        "analytics/positions/<str:stock_code>/",
        PortfolioPositionAnalyticsDetailView.as_view(),
        name="portfolio-position-analytics-detail",
    ),
    path("analytics/cleared/", ClearedPositionListView.as_view(), name="portfolio-cleared-positions"),
]
