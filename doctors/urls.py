"""
doctors/urls.py

URL routing for the doctors app.

  GET    /doctors/                    → DoctorViewSet.list
  GET    /doctors/<pk>/               → DoctorViewSet.retrieve
  PATCH  /doctors/<pk>/               → DoctorViewSet.partial_update (self)
  GET    /doctors/available_now/      → DoctorViewSet.available_now
  POST   /doctors/ping/               → DoctorViewSet.ping (heartbeat)
  POST   /doctors/invite/             → InviteDoctorView (admin)
  PATCH  /doctors/<pk>/verify/        → VerifyDoctorView (admin)
  POST   /doctors/activate/           → ActivateDoctorView (public)
  GET    /doctors/hmo/                → PatientHMOView (list)
  POST   /doctors/hmo/                → PatientHMOView (create)
  DELETE /doctors/hmo/<pk>/           → PatientHMODetailView
  ── NEW ──
  GET    /doctors/availability/       → AvailabilityView (read current settings)
  PATCH  /doctors/availability/       → AvailabilityView (update on-demand + schedule)
  GET    /doctors/slots/              → SlotListCreateView (list upcoming slots)
  POST   /doctors/slots/              → SlotListCreateView (create slot(s))
  PATCH  /doctors/slots/<pk>/         → SlotDetailView (update slot)
  DELETE /doctors/slots/<pk>/         → SlotDetailView (delete slot)
  GET    /doctors/my-schedule/        → MyScheduleView (dashboard)
  GET    /doctors/<pk>/available-weekdays/ → AvailableWeekdaysView (patient calendar)
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActivateDoctorView,
    AvailabilityView,
    AvailableWeekdaysView,
    CompleteDoctorProfileView,
    DoctorViewSet,
    DoctorEarningsView,
    InviteDoctorView,
    MyScheduleView,
    PatientHMODetailView,
    PatientHMOView,
    SlotDetailView,
    SlotListCreateView,
    VerifyDoctorView,
)

router = DefaultRouter()
router.register(r"", DoctorViewSet, basename="doctor")

urlpatterns = [
    # ── Admin / auth ──────────────────────────────────────────────────────────
    path("invite/",             InviteDoctorView.as_view(),     name="doctor-invite"),
    path("activate/",           ActivateDoctorView.as_view(),   name="doctor-activate"),
    path("<int:pk>/verify/",    VerifyDoctorView.as_view(),     name="doctor-verify"),

    # ── Patient HMO cards ─────────────────────────────────────────────────────
    path("hmo/",                PatientHMOView.as_view(),       name="patient-hmo-list"),
    path("hmo/<int:pk>/",       PatientHMODetailView.as_view(), name="patient-hmo-detail"),

    # ── Doctor schedule management (NEW) ──────────────────────────────────────
    # Must be declared BEFORE the router include so the router's catch-all
    # "" pattern does not swallow these named paths.
    path("availability/",       AvailabilityView.as_view(),          name="doctor-availability"),
    path("me/complete/",         CompleteDoctorProfileView.as_view(), name="doctor-profile-complete"),
    path("slots/",               SlotListCreateView.as_view(),        name="doctor-slot-list"),
    path("slots/<int:pk>/",     SlotDetailView.as_view(),       name="doctor-slot-detail"),
    path("my-schedule/",        MyScheduleView.as_view(),       name="doctor-my-schedule"),
    path("earnings/",           DoctorEarningsView.as_view(),   name="doctor-earnings"),
    path("<int:pk>/available-weekdays/", AvailableWeekdaysView.as_view(), name="doctor-available-weekdays"),

    # ── Router (list, retrieve, partial_update, available_now, ping) ──────────
    path("",                    include(router.urls)),
]
