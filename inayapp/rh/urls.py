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
    path("planning", views.planning, name="planning"),
    path("save-planning/", save_planning, name="save_planning"),
    path("update-event/", update_event, name="update_event"),
    path("delete-event/<int:event_id>/", delete_event, name="delete_event"),
    path("planning/print/", print_planning, name="print_planning"),
    path("print-planning/", views.print_planning, name="print_planning"),
    path(
        "validate-presence/<int:event_id>/",
        views.validate_presence,
        name="validate_presence",
    ),
    path(
        "validate-presence-range/",
        views.validate_presence_range,
        name="validate_presence_range",
    ),
    path("sync/attendances/", views.sync_attendances, name="sync_attendances"),
    path("sync/users/", views.sync_users, name="sync_users"),
    path("pointages/", attendance_report, name="attendance_report"),
    path(
        "save-reference-hours/", views.save_reference_hours, name="save_reference_hours"
    ),
    path(
        "salary-advance/create/",
        views.salary_advance_create,
        name="salary_advance_create",
    ),
    path(
        "leave-request/create/", views.leave_request_create, name="leave_request_create"
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path(
        "salary-request/<int:request_id>/<str:action>/",
        views.process_salary_request,
        name="process_salary_request",
    ),
    path(
        "leave-request/<int:request_id>/<str:action>/",
        views.process_leave_request,
        name="process_leave_request",
    ),
]
