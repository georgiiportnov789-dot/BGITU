"""Проверки прав по роли. developer и superuser проходят всё."""
from functools import wraps

from django.core.exceptions import PermissionDenied


def get_role(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', None) if profile else None


def role_can(user, permission):
    """permission — имя булева поля Role, например can_grade."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    role = get_role(user)
    if not role:
        return False
    if role.is_developer:
        return True
    return bool(getattr(role, permission, False))


def role_required(permission):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not role_can(request.user, permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
