# complaints/templatetags/complaint_extras.py
import re

from django import template
from django.utils.html import format_html

from complaints.models import Priority, Status

register = template.Library()

# Status is always rendered as icon + label, never colour alone.
STATUS_STYLE = {
    Status.SUBMITTED: ('warn', 'inbox'),
    Status.SEEN: ('info', 'eye'),
    Status.IN_PROGRESS: ('progress', 'wrench'),
    Status.RESOLVED: ('ok', 'check-circle'),
    Status.REJECTED: ('danger', 'x-circle'),
}

EVENT_ICONS = {'priority': 'flag', 'assignment': 'user', 'ward': 'map'}


@register.simple_tag
def icon(name, css=''):
    return format_html(
        '<svg class="icon {}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>', css, name
    )


@register.simple_tag
def issue_icon(issue_type, css=''):
    return icon(f'issue-{issue_type or "other"}', css)


@register.simple_tag
def status_badge(status, size=''):
    """Accepts a status value (e.g. 'in_progress')."""
    try:
        status = Status(status)
    except ValueError:
        return ''
    tone, name = STATUS_STYLE[status]
    return format_html('<span class="badge {} {}">{}{}</span>', tone, size, icon(name), status.label)


@register.filter
def status_tone(status):
    return STATUS_STYLE.get(status, ('plain', 'info'))[0]


@register.filter
def status_icon_name(status):
    return STATUS_STYLE.get(status, ('plain', 'info'))[1]


@register.filter
def event_icon_name(kind):
    return EVENT_ICONS.get(kind, 'info')


@register.simple_tag
def priority_indicator(priority):
    try:
        priority = Priority(int(priority))
    except (TypeError, ValueError):
        return ''
    return format_html(
        '<span class="prio prio-{}" title="{} priority"><span class="prio-bars" aria-hidden="true">'
        '<i></i><i></i><i></i><i></i></span>{}</span>',
        priority.value, priority.label, priority.label,
    )


@register.simple_tag(takes_context=True)
def querystring_replace(context, **kwargs):
    """Rebuild the current query string with some keys replaced (keeps filters on pagination)."""
    params = context['request'].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def initials(user):
    """
    Up to two initials for an avatar. Splits on separators so "asha.patil"
    and "asha.more" render differently.
    """
    if user is None:
        return '?'
    full = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
    source = full or str(getattr(user, 'username', user))
    parts = [p for p in re.split(r'[\s._\-]+', source) if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return (parts[0][:2] if parts else '?').upper()


@register.filter
def percent_of(value, total):
    """Integer percentage, safe when the total is zero."""
    try:
        total = float(total)
        return round(float(value) / total * 100) if total else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
