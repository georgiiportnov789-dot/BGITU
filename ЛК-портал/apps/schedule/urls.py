from django.urls import path

from . import views

app_name = 'schedule'

urlpatterns = [
    path('schedule/', views.schedule_view, name='schedule'),
    path('schedule/import/', views.import_view, name='import'),
    path('schedule/import/server/', views.import_from_server_file, name='import_server'),
]
