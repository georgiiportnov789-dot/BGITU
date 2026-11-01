"""Роли, профили и заявки на получение роли."""
from django.conf import settings
from django.db import models


class Role(models.Model):
    """Роль в системе. Права — булевы флаги, developer обходит все проверки."""

    code = models.SlugField('код', max_length=40, unique=True)
    name = models.CharField('название', max_length=80)
    description = models.TextField('описание', blank=True)
    can_manage_users = models.BooleanField('управление пользователями', default=False)
    can_manage_roles = models.BooleanField('управление ролями', default=False)
    can_approve_roles = models.BooleanField('рассмотрение заявок на роли', default=False)
    can_manage_schedule = models.BooleanField('управление расписанием', default=False)
    can_create_courses = models.BooleanField('создание курсов', default=False)
    can_grade = models.BooleanField('оценки и ведомости', default=False)
    can_upload_works = models.BooleanField('загрузка работ', default=True)
    can_view_all = models.BooleanField('видит все группы', default=False)
    is_developer = models.BooleanField('разработчик (полный доступ)', default=False)
    is_system = models.BooleanField('системная роль', default=False)
    created_at = models.DateTimeField('создана', auto_now_add=True)

    class Meta:
        verbose_name = 'роль'
        verbose_name_plural = 'роли'
        ordering = ['id']

    def __str__(self):
        return self.name

    @property
    def permission_list(self):
        fields = [
            ('can_manage_users', 'пользователи'),
            ('can_manage_roles', 'роли'),
            ('can_approve_roles', 'заявки на роли'),
            ('can_manage_schedule', 'расписание'),
            ('can_create_courses', 'курсы'),
            ('can_grade', 'оценки'),
            ('can_upload_works', 'работы'),
            ('can_view_all', 'все группы'),
            ('is_developer', 'полный доступ'),
        ]
        return [label for field, label in fields if getattr(self, field)]


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='profiles', null=True, blank=True)
    group = models.ForeignKey('education.Group', on_delete=models.SET_NULL, related_name='profiles', null=True, blank=True)
    record_book = models.CharField('зачётная книжка', max_length=32, blank=True)
    phone = models.CharField('телефон', max_length=32, blank=True)
    birth_date = models.DateField('дата рождения', null=True, blank=True)

    class Meta:
        verbose_name = 'профиль'
        verbose_name_plural = 'профили'

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def display_name(self):
        name = f'{self.user.last_name} {self.user.first_name}'.strip()
        return name or self.user.username


class RoleRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'на рассмотрении'),
        (STATUS_APPROVED, 'одобрена'),
        (STATUS_REJECTED, 'отклонена'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='role_requests')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='requests')
    comment = models.TextField('обоснование', blank=True)
    status = models.CharField('статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField('создана', auto_now_add=True)
    reviewed_at = models.DateTimeField('рассмотрена', null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_role_requests'
    )
    review_comment = models.TextField('комментарий проверяющего', blank=True)

    class Meta:
        verbose_name = 'заявка на роль'
        verbose_name_plural = 'заявки на роль'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} → {self.role} ({self.get_status_display()})'
