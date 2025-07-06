# audit/permissions.py
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class AuditPermissionMixin(UserPassesTestMixin):
    """Mixin pour vérifier les permissions d'audit"""

    def test_func(self):
        return self.request.user.is_staff and (
            self.request.user.is_superuser
            or self.request.user.has_perm("audit.view_auditlog")
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied("Permission d'audit requise")
