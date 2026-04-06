"""
doctors/filters.py

django-filter FilterSet for DoctorProfile.
Supports: specialty, city, on_demand, is_verified, fee ranges, HMO, service.
"""

import django_filters

from .models import DoctorProfile


class DoctorFilter(django_filters.FilterSet):
    """
    Filterset aligned with NowServing.ph search UX:
      - specialty (exact, case-insensitive contains)
      - city (exact)
      - on_demand (boolean)
      - is_verified (boolean)
      - fee_online_lte / fee_online_gte (range)
      - hmo (filter by accepted HMO name)
      - service (filter by offered service name)
    """

    specialty = django_filters.CharFilter(
        field_name="specialty", lookup_expr="icontains"
    )
    city = django_filters.CharFilter(
        field_name="city", lookup_expr="iexact"
    )
    on_demand = django_filters.BooleanFilter(field_name="is_on_demand")
    is_verified = django_filters.BooleanFilter(field_name="is_verified")

    fee_online_lte = django_filters.NumberFilter(
        field_name="consultation_fee_online", lookup_expr="lte"
    )
    fee_online_gte = django_filters.NumberFilter(
        field_name="consultation_fee_online", lookup_expr="gte"
    )
    fee_inperson_lte = django_filters.NumberFilter(
        field_name="consultation_fee_in_person", lookup_expr="lte"
    )
    fee_inperson_gte = django_filters.NumberFilter(
        field_name="consultation_fee_in_person", lookup_expr="gte"
    )

    # Filter by HMO name (e.g. ?hmo=Maxicare)
    hmo = django_filters.CharFilter(
        field_name="hmos__name", lookup_expr="iexact"
    )

    # Filter by service name (e.g. ?service=Medical+Certificate)
    service = django_filters.CharFilter(
        field_name="services__name", lookup_expr="iexact"
    )

    # Filter by hospital/clinic affiliation name
    hospital = django_filters.CharFilter(
        field_name="hospitals__name", lookup_expr="icontains"
    )

    class Meta:
        model = DoctorProfile
        fields = [
            "specialty",
            "city",
            "on_demand",
            "is_verified",
            "fee_online_lte",
            "fee_online_gte",
            "fee_inperson_lte",
            "fee_inperson_gte",
            "hmo",
            "service",
            "hospital",
        ]
