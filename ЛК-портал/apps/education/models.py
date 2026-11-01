"""Группы, курсы, работы, посещаемость и оценки."""
from django.conf import settings
from django.db import models


class Group(models.Model):
    code = models.CharField('код группы', max_length=16, unique=True)
    program = models.CharField('направление', max_length=160, blank=True)
    course = models.PositiveSmallIntegerField('курс', default=1)
    institute = models.CharField('институт', max_length=120, default='Инженерно-экономический институт')
    curator = models.CharField('куратор', max_length=120, blank=True)

    class Meta:
        verbose_name = 'группа'
        verbose_name_plural = 'группы'
        ordering = ['code']

    def __str__(self):
        return self.code


class Course(models.Model):
    title = models.CharField('название', max_length=160)
    code = models.CharField('код', max_length=32)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='courses')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='teaching_courses')
    semester = models.PositiveSmallIntegerField('семестр', default=1)
    description = models.TextField('описание', blank=True)
    created_at = models.DateTimeField('создан', auto_now_add=True)

    class Meta:
        verbose_name = 'курс'
        verbose_name_plural = 'курсы'
        ordering = ['title']
        constraints = [models.UniqueConstraint(fields=['code', 'group'], name='uniq_course_code_group')]

    def __str__(self):
        return f'{self.title} · {self.group.code}'


class Enrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'зачисление'
        verbose_name_plural = 'зачисления'
        constraints = [models.UniqueConstraint(fields=['course', 'student'], name='uniq_enrollment')]

    def __str__(self):
        return f'{self.student} · {self.course}'


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField('название', max_length=180)
    description = models.TextField('описание', blank=True)
    due_date = models.DateField('срок сдачи', null=True, blank=True)
    material = models.FileField('материал', upload_to='materials/%Y/%m/', blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_assignments')
    created_at = models.DateTimeField('создана', auto_now_add=True)

    class Meta:
        verbose_name = 'задание'
        verbose_name_plural = 'задания'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Submission(models.Model):
    STATUS_SUBMITTED = 'submitted'
    STATUS_REVIEWED = 'reviewed'
    STATUS_RETURNED = 'returned'
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, 'на проверке'),
        (STATUS_REVIEWED, 'проверена'),
        (STATUS_RETURNED, 'на доработке'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submissions')
    file = models.FileField('файл работы', upload_to='works/%Y/%m/')
    comment = models.TextField('комментарий', blank=True)
    submitted_at = models.DateTimeField('загружена', auto_now_add=True)
    status = models.CharField('статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    grade = models.CharField('оценка', max_length=16, blank=True)
    teacher_comment = models.TextField('комментарий преподавателя', blank=True)
    reviewed_at = models.DateTimeField('проверена', null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_submissions'
    )

    class Meta:
        verbose_name = 'работа'
        verbose_name_plural = 'работы'
        ordering = ['-submitted_at']
        constraints = [models.UniqueConstraint(fields=['assignment', 'student'], name='uniq_submission')]

    def __str__(self):
        return f'{self.student} · {self.assignment}'


class Attendance(models.Model):
    STATUS_PRESENT = 'present'
    STATUS_ABSENT = 'absent'
    STATUS_LATE = 'late'
    STATUS_EXCUSED = 'excused'
    STATUS_CHOICES = [
        (STATUS_PRESENT, 'был'),
        (STATUS_ABSENT, 'не был'),
        (STATUS_LATE, 'опоздал'),
        (STATUS_EXCUSED, 'уважительная'),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='attendance')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField('дата')
    status = models.CharField('статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='marked_attendance')
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'посещаемость'
        verbose_name_plural = 'посещаемость'
        ordering = ['-date']
        constraints = [models.UniqueConstraint(fields=['course', 'student', 'date'], name='uniq_attendance')]


class Grade(models.Model):
    KIND_EXAM = 'exam'
    KIND_CREDIT = 'credit'
    KIND_COURSEWORK = 'coursework'
    KIND_TEST = 'test'
    KIND_CHOICES = [
        (KIND_EXAM, 'экзамен'),
        (KIND_CREDIT, 'зачёт'),
        (KIND_COURSEWORK, 'курсовая'),
        (KIND_TEST, 'контрольная'),
    ]
    VALUE_CHOICES = [
        ('5', '5'),
        ('4', '4'),
        ('3', '3'),
        ('2', '2'),
        ('зачтено', 'зачтено'),
        ('не зачтено', 'не зачтено'),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='grades')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='grades')
    kind = models.CharField('вид контроля', max_length=16, choices=KIND_CHOICES, default=KIND_EXAM)
    value = models.CharField('оценка', max_length=16, choices=VALUE_CHOICES)
    date = models.DateField('дата')
    comment = models.CharField('комментарий', max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_grades')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'оценка'
        verbose_name_plural = 'оценки'
        ordering = ['-date']
        constraints = [models.UniqueConstraint(fields=['course', 'student', 'kind'], name='uniq_grade_kind')]

    def __str__(self):
        return f'{self.student} · {self.course} · {self.value}'

    @property
    def is_fail(self):
        return self.value in ('2', 'не зачтено')

    @property
    def numeric(self):
        return int(self.value) if self.value in ('2', '3', '4', '5') else None
