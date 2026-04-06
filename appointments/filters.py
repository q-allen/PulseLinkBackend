"""
appointments/filters.py

django-filter FilterSet for Appointment.
Used by the ViewSet's list action for query-param filtering.
"""

import django_filters
from .models import Appointment


class AppointmentFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to   = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model  = Appointment
        fields = {
            "status":         ["exact"],
            "type":           ["exact"],
            "payment_status": ["exact"],
            "doctor":         ["exact"],
            "patient":        ["exact"],
            "date":           ["exact"],
        }
