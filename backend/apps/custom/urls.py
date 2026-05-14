from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomRequestViewSet


router = DefaultRouter()
router.register("", CustomRequestViewSet, basename="custom")

urlpatterns = [
    path("", include(router.urls)),
]
