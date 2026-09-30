# complaints/decorators.py
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .policies import is_corporator


def corporator_required(view_func):
    """
    Restrict a view to corporators.

    Anonymous users are sent to the login page with ?next= preserved, so they
    land back here after signing in; signed-in citizens get a 403.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_corporator(request.user):
            raise PermissionDenied('This area is for municipal corporators only.')
        return view_func(request, *args, **kwargs)

    return wrapper
