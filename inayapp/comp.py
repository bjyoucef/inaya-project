# rh/views.py
import logging
from calendar import c
from collections import defaultdict
from datetime import date, datetime
from datetime import time
from datetime import time as datetime_time
from datetime import timedelta
from io import BytesIO

from accueil.models import ConfigDate
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from xhtml2pdf import pisa

from .models import (
    Attendance,
    Employee,
    LeaveRequest,
    Personnel,
    Planning,
    SalaryAdvanceRequest,
    Services,
)

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def api_events(request):


def extract_filters(request):


def build_redirect_params(filters):


@permission_required("accueil.view_menu_items_plannings", raise_exception=True)
def planning(request):


@permission_required("rh.creer_planning", raise_exception=True)
def save_planning(request):


@permission_required("rh.modifier_planning", raise_exception=True)
def update_event(request):

@permission_required("rh.supprimer_planning", raise_exception=True)
def delete_event(request, event_id):


@permission_required("rh.exporter_planning", raise_exception=True)
def print_planning(request):


@transaction.atomic
@login_required
def validate_presence(request):


def get_date_range(config):



def classify_attendances(attendances, employee, current_date):


def build_pairs(
    entries, exits_list, employee, current_date, next_day_records, next_date
):

def format_duration(seconds):


def format_minutes(seconds):


def attendance_report(request):


@csrf_exempt
def save_reference_hours(request):

@require_POST
def sync_attendances(request):

@require_POST
def sync_users(request):


@login_required
def salary_advance_create(request):


@login_required
def leave_request_create(request):


@login_required
def dashboard(request):


@permission_required("rh.process_salaryadvance_request", raise_exception=True)
@login_required
def process_salary_request(request, request_id, action):


@permission_required("rh.process_leave_request", raise_exception=True)
@login_required
def process_leave_request(request, request_id, action):

