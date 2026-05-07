from rest_framework.routers import DefaultRouter

from .views import TradeRecordViewSet


router = DefaultRouter()
router.register("", TradeRecordViewSet, basename="trade-record")

urlpatterns = router.urls

