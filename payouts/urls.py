"""
payouts/urls.py
"""

from django.urls import path
from .views import (
    AdminRevenueDashboardView,
    DoctorEarningsDashboardView,
    PayoutApproveView,
    PayoutDetailView,
    PayoutListView,
    PayoutRejectView,
    PayoutRequestView,
)

urlpatterns = [
    # Doctor + Admin: list payouts
    path("",                        PayoutListView.as_view(),             name="payout-list"),
    # Doctor: submit payout request
    path("request/",                PayoutRequestView.as_view(),          name="payout-request"),
    # Doctor earnings dashboard
    path("earnings/",               DoctorEarningsDashboardView.as_view(), name="payout-earnings"),
    # Admin: platform revenue dashboard
    path("admin/revenue/",          AdminRevenueDashboardView.as_view(),  name="payout-admin-revenue"),
    # Single payout detail
    path("<int:pk>/",               PayoutDetailView.as_view(),           name="payout-detail"),
    # Admin: approve / reject
    path("<int:pk>/approve/",       PayoutApproveView.as_view(),          name="payout-approve"),
    path("<int:pk>/reject/",        PayoutRejectView.as_view(),           name="payout-reject"),
]
