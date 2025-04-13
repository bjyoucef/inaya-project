# accueil/models.py
from django.db import models
from django.conf import settings


class MenuItems(models.Model):
    route = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    icon = models.CharField(max_length=255)
    permission = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Format: app_label.permission_codename"
    )
    n = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return self.label
    
    class Meta:
        managed = True
        db_table = 'menu_items'
        permissions = (
            ('view_menu_items_helpdesk', 'Peut voir le  helpdesk'),
            ('view_menu_items_dashboard', 'Peut voir le Dashboard'),
            ('view_menu_items_plannings', 'Peut voir le  plannings'),
            ('view_menu_items_documents', 'Peut voir le  documents'),
        )




class ConfigDate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, models.DO_NOTHING, blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    page = models.CharField(max_length=50)

    class Meta:
        managed = True
        db_table = 'config_date'
