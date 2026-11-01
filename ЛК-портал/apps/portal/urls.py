from django.urls import path

from . import views

app_name = 'portal'

urlpatterns = [
    path('', views.home, name='home'),
    path('cabinet/', views.dashboard, name='dashboard'),
    path('cabinet/grades/', views.grades_view, name='grades'),
]
