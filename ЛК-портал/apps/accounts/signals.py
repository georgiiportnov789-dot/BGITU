"""Профили создаются автоматически для каждого пользователя."""
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, Role


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if not created:
        return
    role = Role.objects.filter(code='student').first()
    Profile.objects.get_or_create(user=instance, defaults={'role': role})
