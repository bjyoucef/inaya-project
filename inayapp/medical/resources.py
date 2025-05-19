from import_export import resources, fields
from .models import Service


class ServiceResource(resources.ModelResource):
    class Meta:
        model = Service
        import_id_fields = ["name"]
        fields = ["name", "color", "est_stockeur"]
        skip_unchanged = True
        report_skipped = True
