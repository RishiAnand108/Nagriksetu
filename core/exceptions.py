# core/exceptions.py
"""
One error shape for the whole API.

    {"detail": "Human-readable summary", "code": "machine_code", "errors": {...}}

`errors` appears only for validation failures and maps field names (or
"non_field_errors") to lists of messages, exactly as DRF produces them.
"""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler


class Conflict(APIException):
    """The request is valid but clashes with the complaint's current state."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This action conflicts with the current state of the resource.'
    default_code = 'conflict'


def _first_message(errors):
    if isinstance(errors, dict):
        for value in errors.values():
            message = _first_message(value)
            if message:
                return message
    elif isinstance(errors, (list, tuple)):
        for value in errors:
            message = _first_message(value)
            if message:
                return message
    elif errors:
        return str(errors)
    return ''


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # unhandled → Django's 500 handling and logging

    data = response.data
    if isinstance(exc, ValidationError):
        errors = data if isinstance(data, dict) else {'non_field_errors': data}
        response.data = {
            'detail': _first_message(errors) or 'Invalid input.',
            'code': 'invalid',
            'errors': errors,
        }
        return response

    # DRF converts Django's own exceptions; give them the codes DRF would use.
    if isinstance(exc, Http404):
        response.data = {'detail': 'Not found.', 'code': 'not_found'}
        return response
    if isinstance(exc, PermissionDenied):
        response.data = {'detail': 'You do not have permission to perform this action.', 'code': 'permission_denied'}
        return response

    codes = exc.get_codes() if hasattr(exc, 'get_codes') else None
    if isinstance(codes, dict):
        codes = codes.get('detail') or codes.get('code')
    detail = data.get('detail') if isinstance(data, dict) else _first_message(data)
    response.data = {
        'detail': str(detail or _first_message(data) or 'Request failed.'),
        'code': codes if isinstance(codes, str) else getattr(exc, 'default_code', 'error'),
    }
    return response
