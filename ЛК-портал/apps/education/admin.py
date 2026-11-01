from django.contrib import admin

from .models import Assignment, Attendance, Course, Enrollment, Grade, Group, Submission


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('code', 'course', 'program', 'curator')
    search_fields = ('code',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'code', 'group', 'teacher', 'semester')
    list_filter = ('group', 'semester')
    search_fields = ('title', 'code')


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'enrolled_at')
    list_filter = ('course',)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'due_date', 'created_at')
    list_filter = ('course',)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'status', 'grade', 'submitted_at')
    list_filter = ('status',)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'date', 'status')
    list_filter = ('course', 'status', 'date')


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'kind', 'value', 'date')
    list_filter = ('course', 'kind', 'value')
