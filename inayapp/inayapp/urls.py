from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from accueil.views import update_theme


def custom_permission_denied_view(request, exception=None):
    return render(request, '403.html', status=403)

handler403 = custom_permission_denied_view


urlpatterns = [
    path("select2/", include("django_select2.urls")),
    path("update-theme/", update_theme, name="update_theme"),
    path("", include("accueil.urls")),
    path("admin/", admin.site.urls),
    path("helpdesk/", include("helpdesk.urls")),
    path("documents/", include("documents.urls")),
    path("annuaire/", include("annuaire.urls")),
    path("rh/", include("rh.urls")),
    path("finance/", include("finance.urls")),
    path("patients/", include("patients.urls")),
    path("medecin/", include("medecin.urls")),
    path("medical/", include(("medical.urls", "medical"), namespace="medical")),
]


urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
