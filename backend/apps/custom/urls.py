from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CommissionOptionViewSet, CustomRequestViewSet


router = DefaultRouter()
router.register("options", CommissionOptionViewSet, basename="custom-options")
router.register("", CustomRequestViewSet, basename="custom")

urlpatterns = [
    path("", include(router.urls)),
]
