from rest_framework.views import exception_handler

from .response import fail


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = detail["detail"]
    else:
        message = detail

    return fail(message=message, code=response.status_code, data=detail, status=response.status_code)
