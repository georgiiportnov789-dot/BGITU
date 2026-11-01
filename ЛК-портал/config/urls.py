"""Корневые URL проекта."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.portal.urls')),
    path('', include('apps.accounts.urls')),
    path('', include('apps.education.urls')),
    path('', include('apps.schedule.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

handler403 = 'apps.core.views.handler403'
handler404 = 'apps.core.views.handler404'
