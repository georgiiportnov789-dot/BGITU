"""Во всех шаблонах доступны роль и флаги текущего пользователя."""
from .permissions import get_role, role_can

PERMISSIONS = {
    'can_manage_users': 'can_manage_users',
    'can_manage_roles': 'can_manage_roles',
    'can_approve_roles': 'can_approve_roles',
    'can_manage_schedule': 'can_manage_schedule',
    'can_create_courses': 'can_create_courses',
    'can_grade': 'can_grade',
    'can_upload_works': 'can_upload_works',
    'can_view_all': 'can_view_all',
    'is_developer': 'is_developer',
}


THEMES = ('paper', 'surik', 'latun', 'brass')


def ui_theme(cookie_value):
    """Тема: выбор в профиле, иначе cookie браузера, иначе «Бумага»."""
    return cookie_value if cookie_value in THEMES else 'paper'


def role_context(request):
    user = getattr(request, 'user', None)
    cookie = request.COOKIES.get('bgitu-theme', '')
    if not user or not user.is_authenticated:
        return {'current_role': None, 'perms': {}, 'ui_theme': ui_theme(cookie)}
    profile = getattr(user, 'profile', None)
    chosen = (profile.theme if profile and profile.theme else '') or cookie
    return {
        'current_role': get_role(user),
        'perms': {key: role_can(user, field) for key, field in PERMISSIONS.items()},
        'ui_theme': ui_theme(chosen),
    }
    return {
        'current_role': get_role(user),
        'perms': {key: role_can(user, field) for key, field in PERMISSIONS.items()},
    }
