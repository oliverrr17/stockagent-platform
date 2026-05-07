from rest_framework.routers import DefaultRouter

from .views import NewsItemViewSet, NotificationLogViewSet


router = DefaultRouter()
router.register("notifications", NotificationLogViewSet, basename="notification-log")
router.register("", NewsItemViewSet, basename="news-item")

urlpatterns = router.urls
