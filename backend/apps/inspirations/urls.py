from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import InspirationViewSet


router = DefaultRouter()
router.register("", InspirationViewSet, basename="inspirations")

urlpatterns = [
    path("", include(router.urls)),
]
