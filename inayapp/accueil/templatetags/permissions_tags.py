# accueil/templatetags/permissions_tags.py
from django import template

register = template.Library()

@register.filter(name="has_privilege")
def has_privilege(user, permission_codename):
    return user.has_perm(permission_codename) if permission_codename else True

