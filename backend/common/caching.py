from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response


class CachedPublicReadMixin:
    public_cache_timeout = settings.PUBLIC_API_CACHE_TIMEOUT

    def _public_cache_enabled(self):
        return (
            self.public_cache_timeout > 0
            and self.request.method == "GET"
            and not self.request.user.is_authenticated
        )

    def _public_cache_key(self):
        return f"public-api:{self.request.get_full_path()}"

    def _cached_response(self, builder):
        if not self._public_cache_enabled():
            return builder()

        key = self._public_cache_key()
        cached = cache.get(key)
        if cached is not None:
            return Response(cached["data"], status=cached["status"])

        response = builder()
        if response.status_code == 200:
            cache.set(
                key,
                {"data": response.data, "status": response.status_code},
                self.public_cache_timeout,
            )
        return response

    def list(self, request, *args, **kwargs):
        return self._cached_response(lambda: super(CachedPublicReadMixin, self).list(request, *args, **kwargs))

    def retrieve(self, request, *args, **kwargs):
        return self._cached_response(lambda: super(CachedPublicReadMixin, self).retrieve(request, *args, **kwargs))
