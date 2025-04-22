from django.urls import path
from . import views
from .views import (
    save_planning,
    update_event,
    delete_event,
    print_planning,
    attendance_report,

)


urlpatterns = [
    path("calendar/", views.CalendarView.as_view(), name="calendar"),
    path("rendezvous-json/", views.rendezvous_json, name="rendezvous_json"),
]
