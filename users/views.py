# users/views.py
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from complaints import services as complaint_services
from complaints.models import Complaint
from core.http import safe_next
from core.ratelimit import login_throttled

from . import services
from .forms import ProfileForm, SignupForm, StyledAuthenticationForm


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        services.send_verification_email(request, user)
        greeting = f'Welcome to NagrikSetu, {user.username}.'
        if user.email:
            greeting += f' We sent a confirmation link to {user.email}.'
        messages.success(request, greeting)
        return redirect(safe_next(request, reverse('dashboard')))

    return render(request, 'users/signup.html', {'form': form})


@login_throttled
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = StyledAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(safe_next(request, reverse('dashboard')))

    return render(request, 'users/login.html', {'form': form, 'next': safe_next(request, '')})


@require_POST
def logout_view(request):
    """
    POST-only.

    A GET logout can be triggered by any image tag or prefetch on a page the
    user visits, which is a CSRF hole and breaks link prefetching.
    """
    logout(request)
    messages.info(request, 'You have been signed out.')
    return redirect('login')


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST':
        if form.is_valid():
            user = form.save()
            if form.email_changed and user.email:
                services.send_verification_email(request, user)
                messages.success(request, f'Profile saved. Check {user.email} for a confirmation link.')
            else:
                messages.success(request, 'Profile saved.')
            return redirect('profile')
        messages.error(request, 'Please fix the highlighted fields.')

    own = Complaint.objects.filter(user=request.user)
    return render(request, 'users/profile.html', {
        'form': form,
        'stats': complaint_services.dashboard_stats(own),
    })


@login_required
@require_POST
def resend_verification(request):
    user = request.user
    if not user.email:
        messages.error(request, 'Add an email address first.')
    elif user.email_verified:
        messages.info(request, 'Your email address is already confirmed.')
    else:
        services.send_verification_email(request, user)
        messages.success(request, f'We sent a new confirmation link to {user.email}.')
    return redirect('profile')


def verify_email(request, token):
    user = services.verify_token(token)
    if user is None:
        messages.error(request, 'That confirmation link is invalid or has expired. You can request a new one '
                                'from your profile.')
    else:
        messages.success(request, f'Thanks — {user.email} is confirmed. You will now get complaint updates.')
    return redirect('profile' if request.user.is_authenticated else 'login')
