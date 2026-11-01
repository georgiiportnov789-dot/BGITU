"""Служебные представления: healthcheck и страницы ошибок."""
from django.http import JsonResponse
from django.shortcuts import render


def health(request):
    return JsonResponse({'status': 'ok', 'service': 'bgitu-portal'})


def handler403(request, exception=None):
    return render(request, 'errors/403.html', status=403)


def handler404(request, exception=None):
    return render(request, 'errors/404.html', status=404)
