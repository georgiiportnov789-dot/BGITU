from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('roles/', views.roles_view, name='roles'),
    path('roles/new/', views.role_create, name='role_create'),
    path('roles/<int:role_id>/request/', views.role_request_create, name='role_request_create'),
    path('role-requests/', views.role_requests_view, name='role_requests'),
    path('role-requests/<int:request_id>/<str:action>/', views.role_request_review, name='role_request_review'),
    path('manage/students/', views.manage_students, name='students'),
    path('manage/students/<int:user_id>/', views.manage_student_update, name='student_update'),
]
