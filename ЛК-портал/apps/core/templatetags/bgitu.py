"""Шаблонные фильтры проекта."""
from django import template

register = template.Library()


@register.filter
def ru_num(value):
    if value is None or value == '':
        return '—'
    return str(value).replace('.', ',')


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return None
    return mapping.get(key)


@register.filter
def percent(part, total):
    try:
        return round(int(part) / int(total) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def fio(user):
    """«Портнов Георгий» — фамилия, затем имя (в User поля наоборот)."""
    if not user:
        return ''
    name = f'{getattr(user, "last_name", "")} {getattr(user, "first_name", "")}'.strip()
    return name or getattr(user, 'username', '')


@register.filter
def money(value):
    try:
        return f'{int(value):,}'.replace(',', '\u00a0')
    except (TypeError, ValueError):
        return value
