"""Вход, роли, заявки на роли, управление пользователями."""
import re

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.education.models import Group

from .models import Profile, Role, RoleRequest
from .permissions import get_role, role_can, role_required

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_.@+-]{3,30}$')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('portal:dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, 'Неверный логин или пароль.')
        else:
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next') or '/cabinet/'
            if not next_url.startswith('/') or next_url.startswith('//'):
                next_url = '/cabinet/'
            return redirect(next_url)
    return render(request, 'accounts/login.html', {'next': request.GET.get('next', '')})


def register_view(request):
    """Самостоятельная регистрация: профиль создаётся сразу, роль — «Студент»."""
    if request.user.is_authenticated:
        return redirect('portal:dashboard')

    groups = Group.objects.order_by('course', 'code')
    if request.method == 'POST':
        data = {
            field: request.POST.get(field, '').strip()
            for field in ('last_name', 'first_name', 'username', 'email', 'group')
        }
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        errors = []

        if not data['last_name'] or not data['first_name']:
            errors.append('Укажите фамилию и имя.')
        if not _USERNAME_RE.fullmatch(data['username']):
            errors.append('Логин: 3–30 символов, латиница, цифры, точка, дефис, подчёркивание.')
        elif User.objects.filter(username__iexact=data['username']).exists():
            errors.append('Такой логин уже занят.')
        try:
            validate_email(data['email'])
        except ValidationError:
            errors.append('Укажите корректный e-mail.')
        else:
            if User.objects.filter(email__iexact=data['email']).exists():
                errors.append('На этот e-mail уже зарегистрирован кабинет.')

        group = None
        if data['group']:
            group = Group.objects.filter(pk=data['group']).first()
            if group is None:
                errors.append('Выбранная группа не найдена.')

        if len(password1) < 8:
            errors.append('Пароль должен быть не короче 8 символов.')
        elif password1 != password2:
            errors.append('Пароли не совпадают.')
        else:
            try:
                validate_password(password1)
            except ValidationError as error:
                errors.extend(error.messages)

        if not errors:
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=password1,
                first_name=data['first_name'],
                last_name=data['last_name'],
            )
            profile = getattr(user, 'profile', None) or Profile.objects.create(user=user)
            profile.group = group
            profile.role = Role.objects.filter(code='student').first() or Role.objects.filter(is_system=True).first()
            profile.save(update_fields=['group', 'role'])
            login(request, user)
            messages.success(request, 'Кабинет создан. Добро пожаловать!')
            return redirect('portal:dashboard')

        return render(request, 'accounts/register.html', {
            'groups': groups,
            'form_data': data,
            'errors': errors,
        })

    return render(request, 'accounts/register.html', {'groups': groups, 'form_data': {}, 'errors': []})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, 'Вы вышли из кабинета.')
    return redirect('accounts:login')


@login_required
def roles_view(request):
    roles = Role.objects.annotate(users_count=Count('profiles'))
    profile = getattr(request.user, 'profile', None)
    my_requests = RoleRequest.objects.filter(user=request.user).select_related('role')[:10]
    pending = RoleRequest.objects.filter(status=RoleRequest.STATUS_PENDING).count() if role_can(
        request.user, 'can_approve_roles'
    ) else 0
    return render(request, 'accounts/roles.html', {
        'roles': roles,
        'profile': profile,
        'my_requests': my_requests,
        'pending_count': pending,
        'can_manage_roles': role_can(request.user, 'can_manage_roles'),
        'can_approve_roles': role_can(request.user, 'can_approve_roles'),
    })


@login_required
@require_POST
def role_request_create(request, role_id):
    role = get_object_or_404(Role, pk=role_id)
    profile = getattr(request.user, 'profile', None)
    if profile and profile.role_id == role.id:
        messages.info(request, f'Роль «{role.name}» уже назначена.')
        return redirect('accounts:roles')
    if RoleRequest.objects.filter(user=request.user, role=role, status=RoleRequest.STATUS_PENDING).exists():
        messages.info(request, f'Заявка на роль «{role.name}» уже на рассмотрении.')
        return redirect('accounts:roles')
    RoleRequest.objects.create(
        user=request.user,
        role=role,
        comment=request.POST.get('comment', '').strip()[:1000],
    )
    messages.success(request, f'Заявка на роль «{role.name}» отправлена.')
    return redirect('accounts:roles')


@login_required
def role_requests_view(request):
    can_review = role_can(request.user, 'can_approve_roles')
    if can_review:
        requests_qs = RoleRequest.objects.select_related('user', 'role', 'reviewed_by')
    else:
        requests_qs = RoleRequest.objects.filter(user=request.user).select_related('role')
    return render(request, 'accounts/role_requests.html', {
        'requests': requests_qs,
        'can_review': can_review,
        'pending_count': requests_qs.filter(status=RoleRequest.STATUS_PENDING).count(),
    })


@login_required
@require_POST
def role_request_review(request, request_id, action):
    if not role_can(request.user, 'can_approve_roles'):
        messages.error(request, 'Недостаточно прав для рассмотрения заявок.')
        return redirect('accounts:role_requests')
    role_request = get_object_or_404(RoleRequest.objects.select_related('role', 'user'), pk=request_id)
    if role_request.status != RoleRequest.STATUS_PENDING:
        messages.info(request, 'Заявка уже рассмотрена.')
        return redirect('accounts:role_requests')
    if role_request.role.is_developer and not role_can(request.user, 'is_developer'):
        messages.error(request, 'Роль разработчика может выдавать только разработчик.')
        return redirect('accounts:role_requests')
    if action not in ('approve', 'reject'):
        messages.error(request, 'Неизвестное действие.')
        return redirect('accounts:role_requests')

    role_request.status = RoleRequest.STATUS_APPROVED if action == 'approve' else RoleRequest.STATUS_REJECTED
    role_request.reviewed_at = timezone.now()
    role_request.reviewed_by = request.user
    role_request.review_comment = request.POST.get('review_comment', '').strip()[:1000]
    role_request.save()

    if action == 'approve':
        profile, _ = Profile.objects.get_or_create(user=role_request.user)
        profile.role = role_request.role
        profile.save(update_fields=['role'])
        messages.success(request, f'Роль «{role_request.role.name}» выдана пользователю {role_request.user}.')
    else:
        messages.info(request, 'Заявка отклонена.')
    return redirect('accounts:role_requests')


@login_required
@role_required('can_manage_roles')
def role_create(request):
    is_developer = role_can(request.user, 'is_developer')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().lower()
        description = request.POST.get('description', '').strip()
        errors = []
        if len(name) < 2:
            errors.append('Укажите название роли.')
        if not re.fullmatch(r'[a-z][a-z0-9_]{2,39}', code):
            errors.append('Код: латиница, цифры и подчёркивание, от 3 до 40 символов.')
        if Role.objects.filter(code=code).exists():
            errors.append('Роль с таким кодом уже есть.')
        flags = {}
        for field in (
            'can_manage_users', 'can_manage_roles', 'can_manage_schedule', 'can_create_courses',
            'can_grade', 'can_upload_works', 'can_view_all', 'is_developer',
        ):
            flags[field] = request.POST.get(field) == 'on'
        if flags['is_developer'] and not is_developer:
            errors.append('Только разработчик может создать роль с полным доступом.')
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'accounts/role_form.html', {
                'form_data': request.POST,
                'is_developer': is_developer,
            })
        Role.objects.create(name=name, code=code, description=description, is_system=False, **flags)
        messages.success(request, f'Роль «{name}» создана.')
        return redirect('accounts:roles')
    return render(request, 'accounts/role_form.html', {'is_developer': is_developer})


@login_required
@role_required('can_manage_users')
def manage_students(request):
    query = request.GET.get('q', '').strip()
    profiles = Profile.objects.select_related('user', 'role', 'group').order_by('group__code', 'user__last_name')
    if query:
        profiles = profiles.filter(user__username__icontains=query) | profiles.filter(
            user__last_name__icontains=query
        ) | profiles.filter(user__first_name__icontains=query)
        profiles = profiles.distinct()
    return render(request, 'accounts/students.html', {
        'profiles': profiles,
        'groups': Group.objects.all(),
        'roles': Role.objects.all(),
        'query': query,
        'is_developer': role_can(request.user, 'is_developer'),
    })


@login_required
@role_required('can_manage_users')
@require_POST
def manage_student_update(request, user_id):
    profile = get_object_or_404(Profile.objects.select_related('user', 'role'), user__id=user_id)
    role_id = request.POST.get('role')
    group_id = request.POST.get('group') or None
    record_book = request.POST.get('record_book', '').strip()[:32]

    role = Role.objects.filter(pk=role_id).first() if role_id else None
    if role is None:
        messages.error(request, 'Выберите роль из списка.')
        return redirect('accounts:students')
    if role.is_developer and not role_can(request.user, 'is_developer'):
        messages.error(request, 'Роль разработчика может назначать только разработчик.')
        return redirect('accounts:students')
    group = Group.objects.filter(pk=group_id).first() if group_id else None
    profile.role = role
    profile.group = group
    profile.record_book = record_book
    profile.save(update_fields=['role', 'group', 'record_book'])
    messages.success(request, f'Профиль {profile.display_name} обновлён.')
    return redirect('accounts:students')
