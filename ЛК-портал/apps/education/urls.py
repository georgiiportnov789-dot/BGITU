from django.urls import path

from . import views

app_name = 'education'

urlpatterns = [
    path('courses/', views.course_list, name='courses'),
    path('courses/new/', views.course_create, name='course_create'),
    path('courses/<int:course_id>/', views.course_detail, name='course_detail'),
    path('courses/<int:course_id>/journal/', views.course_journal, name='journal'),
    path('courses/<int:course_id>/grade/', views.set_grade, name='set_grade'),
    path('courses/<int:course_id>/assignment/', views.assignment_create, name='assignment_create'),
    path('courses/<int:course_id>/attendance/', views.attendance_view, name='attendance'),
    path('assignments/<int:assignment_id>/submit/', views.submit_work, name='submit_work'),
    path('submissions/<int:submission_id>/review/', views.review_submission, name='review_submission'),
    path('works/', views.my_works, name='works'),
]
