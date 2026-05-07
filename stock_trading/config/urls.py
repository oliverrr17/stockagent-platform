from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .status_views import OperationsActionView, OperationsStatusView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/status/operations/", OperationsStatusView.as_view(), name="operations_status"),
    path("api/status/actions/<str:action>/", OperationsActionView.as_view(), name="operations_action"),
    path("api/trades/", include("trades.urls")),
    path("api/portfolio/", include("portfolio.urls")),
    path("api/analysis/", include("analysis.urls")),
    path("api/news/", include("news.urls")),
]
