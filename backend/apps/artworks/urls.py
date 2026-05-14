from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ArtworkViewSet


router = DefaultRouter()
router.register("", ArtworkViewSet, basename="artworks")

urlpatterns = [
    path("", include(router.urls)),
]
