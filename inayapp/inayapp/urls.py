from accueil.views import update_theme
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path
import nested_admin

def custom_permission_denied_view(request, exception=None):
    return render(request, '403.html', status=403)

handler403 = custom_permission_denied_view


urlpatterns = [
    path("update-theme/", update_theme, name="update_theme"),
    path("", include("accueil.urls")),
    path("admin/", admin.site.urls),
    path("export/", include("export_data.urls")),
    path("helpdesk/", include("helpdesk.urls")),
    path("documents/", include("documents.urls")),
    path("annuaire/", include("annuaire.urls")),
    path("rh/", include("rh.urls")),
    path("finance/", include("finance.urls")),
    path("patients/", include("patients.urls")),
    path("medecin/", include("medecin.urls")),
    path("medical/", include(("medical.urls", "medical"), namespace="medical")),
    path("pharmacies/", include("pharmacies.urls")),
    path("api-auth/", include("rest_framework.urls")),
    path(
        "inventaire/",
        include(("inventaire.urls", "inventaire"), namespace="inventaire"),
    ),
    path("audit/", include(("audit.urls", "audit"), namespace="audit")),
]


urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),  # Version 4.0+
    ] + urlpatterns
