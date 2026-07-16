from rest_framework.response import Response


def ok(data=None, message="success", code=200, status=200):
    return Response({"code": code, "message": message, "data": data}, status=status)


def fail(message="error", code=400, data=None, status=400):
    return Response({"code": code, "message": message, "data": data}, status=status)


class ApiResponseMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if not isinstance(response, Response):
            return response
        if isinstance(response.data, dict) and {"code", "message", "data"} <= set(response.data):
            return response
        response.data = {
            "code": response.status_code,
            "message": "success" if response.status_code < 400 else "error",
            "data": response.data,
        }
        return response
