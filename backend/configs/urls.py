from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def api_home(request):
    return JsonResponse(
        {
            "code": 200,
            "message": "success",
            "data": {
                "project": "星野樱的动漫工作室",
                "frontend": "http://127.0.0.1:5173/",
                "health": "/api/health/",
                "api": {
                    "users": "/api/users/",
                    "artworks": "/api/artworks/",
                    "orders": "/api/orders/",
                    "custom": "/api/custom/",
                    "reviews": "/api/reviews/",
                    "inspirations": "/api/inspirations/",
<<<<<<< HEAD
                    "recommend": "/api/recommend/",
=======
>>>>>>> origin/group_code
                },
            },
        },
        json_dumps_params={"ensure_ascii": False},
    )


def health_check(request):
    return JsonResponse(
        {
            "code": 200,
            "message": "success",
            "data": {"status": "ok", "service": "star_sakura"},
        }
    )


urlpatterns = [
    path("", api_home),
    path("admin/", admin.site.urls),
    path("api/health/", health_check),
    path("api/users/", include("apps.users.urls")),
    path("api/artworks/", include("apps.artworks.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/custom/", include("apps.custom.urls")),
    path("api/reviews/", include("apps.reviews.urls")),
    path("api/inspirations/", include("apps.inspirations.urls")),
<<<<<<< HEAD
    path("api/recommend/", include("apps.recommendations.urls")),
=======
>>>>>>> origin/group_code
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
