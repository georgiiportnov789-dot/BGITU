"""Учебный процесс: курсы, задания, работы, посещаемость, ведомости."""
import datetime
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Profile
from apps.accounts.permissions import role_can, role_required

from .models import Assignment, Attendance, Course, Enrollment, Grade, Submission, Group

ALLOWED_WORK_EXT = {'.pdf', '.doc', '.docx', '.zip', '.rar', '.txt', '.py', '.xlsx', '.png', '.jpg', '.jpeg'}
MAX_WORK_SIZE = 20 * 1024 * 1024


def can_access_course(user, course):
    if role_can(user, 'can_view_all'):
        return True
    if course.teacher_id == user.id:
        return True
    return Enrollment.objects.filter(course=course, student=user).exists()


def is_course_teacher(user, course):
    return course.teacher_id == user.id or role_can(user, 'can_view_all')


def parse_date(value, default=None):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


@login_required
def course_list(request):
    if role_can(request.user, 'can_view_all'):
        courses = Course.objects.select_related('group', 'teacher')
        mode = 'all'
    elif role_can(request.user, 'can_create_courses'):
        courses = Course.objects.filter(teacher=request.user).select_related('group', 'teacher')
        mode = 'teaching'
    else:
        courses = Course.objects.filter(enrollments__student=request.user).select_related('group', 'teacher')
        mode = 'student'
    courses = courses.annotate(
        students_count=Count('enrollments', distinct=True),
        assignments_count=Count('assignments', distinct=True),
    )
    return render(request, 'education/courses.html', {
        'courses': courses,
        'mode': mode,
        'can_create': role_can(request.user, 'can_create_courses'),
    })


@login_required
@role_required('can_create_courses')
def course_create(request):
    groups = Group.objects.all()
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        code = request.POST.get('code', '').strip().upper()
        group_id = request.POST.get('group')
        semester = request.POST.get('semester', '1')
        description = request.POST.get('description', '').strip()
        group = Group.objects.filter(pk=group_id).first()
        errors = []
        if len(title) < 3:
            errors.append('Название курса — минимум 3 символа.')
        if not code:
            errors.append('Укажите код курса.')
        if group is None:
            errors.append('Выберите группу.')
        if not semester.isdigit() or not 1 <= int(semester) <= 12:
            errors.append('Семестр — число от 1 до 12.')
        if group and Course.objects.filter(code=code, group=group).exists():
            errors.append('Курс с таким кодом у группы уже есть.')
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'education/course_form.html', {
                'groups': groups,
                'form_data': request.POST,
            })
        course = Course.objects.create(
            title=title, code=code, group=group, teacher=request.user,
            semester=int(semester), description=description,
        )
        students = Profile.objects.filter(
            group=group, user__is_active=True, role__code__in=['student', 'monitor']
        ).values_list('user_id', flat=True)
        Enrollment.objects.bulk_create(
            [Enrollment(course=course, student_id=sid) for sid in students], ignore_conflicts=True
        )
        messages.success(request, f'Курс «{title}» создан, зачислено студентов: {len(students)}.')
        return redirect('education:course_detail', course_id=course.id)
    return render(request, 'education/course_form.html', {'groups': groups})


@login_required
def course_detail(request, course_id):
    course = get_object_or_404(Course.objects.select_related('group', 'teacher'), pk=course_id)
    if not can_access_course(request.user, course):
        raise PermissionDenied
    assignments = course.assignments.annotate(submissions_count=Count('submissions')).order_by('-created_at')
    my_submissions = {
        s.assignment_id: s
        for s in Submission.objects.filter(assignment__course=course, student=request.user)
    }
    submissions_to_review = Submission.objects.filter(
        assignment__course=course, status=Submission.STATUS_SUBMITTED
    ).select_related('student', 'assignment').order_by('-submitted_at') if is_course_teacher(request.user, course) else []
    return render(request, 'education/course_detail.html', {
        'course': course,
        'assignments': assignments,
        'my_submissions': my_submissions,
        'submissions_to_review': submissions_to_review,
        'is_teacher': is_course_teacher(request.user, course),
        'is_enrolled': Enrollment.objects.filter(course=course, student=request.user).exists(),
    })


@login_required
@require_POST
def submit_work(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related('course'), pk=assignment_id)
    course = assignment.course
    if not Enrollment.objects.filter(course=course, student=request.user).exists():
        messages.error(request, 'Вы не записаны на этот курс.')
        return redirect('education:courses')

    upload = request.FILES.get('file')
    if upload is None:
        messages.error(request, 'Приложите файл работы.')
        return redirect('education:course_detail', course_id=course.id)
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in ALLOWED_WORK_EXT:
        messages.error(request, 'Формат файла не поддерживается: ' + ', '.join(sorted(ALLOWED_WORK_EXT)))
        return redirect('education:course_detail', course_id=course.id)
    if upload.size > MAX_WORK_SIZE:
        messages.error(request, 'Файл больше 20 МБ.')
        return redirect('education:course_detail', course_id=course.id)

    existing = Submission.objects.filter(assignment=assignment, student=request.user).first()
    if existing and existing.status != Submission.STATUS_RETURNED:
        messages.error(request, 'Работа уже загружена — дождитесь проверки.')
        return redirect('education:course_detail', course_id=course.id)
    if existing:
        existing.file = upload
        existing.comment = request.POST.get('comment', '').strip()[:2000]
        existing.status = Submission.STATUS_SUBMITTED
        existing.grade = ''
        existing.teacher_comment = ''
        existing.reviewed_at = None
        existing.reviewed_by = None
        existing.save()
    else:
        Submission.objects.create(
            assignment=assignment,
            student=request.user,
            file=upload,
            comment=request.POST.get('comment', '').strip()[:2000],
        )
    messages.success(request, 'Работа загружена и отправлена на проверку.')
    return redirect('education:course_detail', course_id=course.id)


@login_required
def my_works(request):
    submissions = Submission.objects.filter(student=request.user).select_related('assignment', 'assignment__course')
    return render(request, 'education/works.html', {'submissions': submissions})


@login_required
def course_journal(request, course_id):
    course = get_object_or_404(Course.objects.select_related('group', 'teacher'), pk=course_id)
    if not role_can(request.user, 'can_grade') or not is_course_teacher(request.user, course):
        raise PermissionDenied
    enrollments = course.enrollments.select_related('student', 'student__profile').order_by(
        'student__last_name', 'student__first_name'
    )
    grades = {g.student_id: g for g in Grade.objects.filter(course=course)}
    attendance = {
        row['student_id']: row
        for row in Attendance.objects.filter(course=course).values('student_id').annotate(
            present=Count('id', filter=Q(status=Attendance.STATUS_PRESENT)),
            absent=Count('id', filter=Q(status=Attendance.STATUS_ABSENT)),
            late=Count('id', filter=Q(status=Attendance.STATUS_LATE)),
        )
    }
    rows = []
    for enrollment in enrollments:
        student = enrollment.student
        row = {
            'student': student,
            'profile': getattr(student, 'profile', None),
            'exam': grades.get(student.id),
            'attendance': attendance.get(student.id, {'present': 0, 'absent': 0, 'late': 0}),
        }
        rows.append(row)
    kinds = Grade.KIND_CHOICES
    return render(request, 'education/journal.html', {
        'course': course,
        'rows': rows,
        'kinds': kinds,
        'values': Grade.VALUE_CHOICES,
        'today': timezone.localdate(),
        'assignments': course.assignments.annotate(submissions_count=Count('submissions')),
    })


@login_required
@require_POST
def set_grade(request, course_id):
    course = get_object_or_404(Course.objects.select_related('teacher'), pk=course_id)
    if not role_can(request.user, 'can_grade') or not is_course_teacher(request.user, course):
        raise PermissionDenied
    student_id = request.POST.get('student')
    kind = request.POST.get('kind')
    value = request.POST.get('value')
    date = parse_date(request.POST.get('date'), timezone.localdate())
    if not Enrollment.objects.filter(course=course, student_id=student_id).exists():
        messages.error(request, 'Студент не записан на курс.')
        return redirect('education:journal', course_id=course.id)
    if kind not in dict(Grade.KIND_CHOICES) or value not in dict(Grade.VALUE_CHOICES):
        messages.error(request, 'Некорректная оценка или вид контроля.')
        return redirect('education:journal', course_id=course.id)
    Grade.objects.update_or_create(
        course=course,
        student_id=student_id,
        kind=kind,
        defaults={
            'value': value,
            'date': date,
            'comment': request.POST.get('comment', '').strip()[:200],
            'created_by': request.user,
        },
    )
    messages.success(request, 'Оценка сохранена.')
    return redirect('education:journal', course_id=course.id)


@login_required
@role_required('can_create_courses')
@require_POST
def assignment_create(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not is_course_teacher(request.user, course):
        raise PermissionDenied
    title = request.POST.get('title', '').strip()
    if len(title) < 3:
        messages.error(request, 'Название задания — минимум 3 символа.')
        return redirect('education:journal', course_id=course.id)
    Assignment.objects.create(
        course=course,
        title=title,
        description=request.POST.get('description', '').strip()[:4000],
        due_date=parse_date(request.POST.get('due_date')),
        material=request.FILES.get('material') or '',
        created_by=request.user,
    )
    messages.success(request, 'Задание добавлено.')
    if request.POST.get('next') == 'journal':
        return redirect('education:journal', course_id=course.id)
    return redirect('education:course_detail', course_id=course.id)


@login_required
@require_POST
def review_submission(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related('assignment', 'assignment__course'), pk=submission_id
    )
    course = submission.assignment.course
    if not role_can(request.user, 'can_grade') or not is_course_teacher(request.user, course):
        raise PermissionDenied
    status = request.POST.get('status')
    if status not in (Submission.STATUS_REVIEWED, Submission.STATUS_RETURNED):
        messages.error(request, 'Некорректный статус проверки.')
        return redirect('education:course_detail', course_id=course.id)
    submission.status = status
    submission.grade = request.POST.get('grade', '').strip()[:16]
    submission.teacher_comment = request.POST.get('teacher_comment', '').strip()[:4000]
    submission.reviewed_at = timezone.now()
    submission.reviewed_by = request.user
    submission.save()
    messages.success(request, 'Работа проверена.')
    return redirect('education:course_detail', course_id=course.id)


@login_required
def attendance_view(request, course_id):
    course = get_object_or_404(Course.objects.select_related('teacher'), pk=course_id)
    if not role_can(request.user, 'can_grade') or not is_course_teacher(request.user, course):
        raise PermissionDenied
    date = parse_date(request.GET.get('date'), timezone.localdate())
    enrollments = course.enrollments.select_related('student').order_by('student__last_name', 'student__first_name')
    existing = {a.student_id: a.status for a in Attendance.objects.filter(course=course, date=date)}

    if request.method == 'POST':
        date = parse_date(request.POST.get('date'), date)
        valid_statuses = dict(Attendance.STATUS_CHOICES)
        saved = 0
        for enrollment in enrollments:
            status = request.POST.get(f'status_{enrollment.student_id}')
            if status not in valid_statuses:
                continue
            Attendance.objects.update_or_create(
                course=course,
                student=enrollment.student,
                date=date,
                defaults={'status': status, 'marked_by': request.user},
            )
            saved += 1
        messages.success(request, f'Посещаемость за {date:%d.%m.%Y} сохранена ({saved} студентов).')
        return redirect(f"{request.path}?date={date.isoformat()}")

    rows = [{'student': e.student, 'status': existing.get(e.student_id, Attendance.STATUS_PRESENT)} for e in enrollments]
    return render(request, 'education/attendance.html', {
        'course': course,
        'rows': rows,
        'date': date,
        'statuses': Attendance.STATUS_CHOICES,
    })
