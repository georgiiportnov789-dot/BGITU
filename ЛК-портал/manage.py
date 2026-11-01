#!/usr/bin/env python
"""Утилита управления проектом БГИТУ-портал."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'Не найден Django. Активируйте окружение: source .venv/bin/activate'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
