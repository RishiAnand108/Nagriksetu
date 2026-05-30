# complaints/decorators.py
from django.core.exceptions import PermissionDenied

def corporator_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect('login')
        if request.user.role != 'corporator':
            raise PermissionDenied   # shows 403 page
        return view_func(request, *args, **kwargs)
    return wrapper