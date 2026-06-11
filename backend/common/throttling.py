from rest_framework.permissions import SAFE_METHODS


class WriteScopedThrottleMixin:
    write_throttle_scope = "write"

    def get_throttles(self):
        if self.request.method not in SAFE_METHODS:
            self.throttle_scope = self.write_throttle_scope
        return super().get_throttles()
