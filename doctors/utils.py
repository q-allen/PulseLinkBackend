"""
doctors/utils.py

Helper functions for schedule/slot management.

  generate_slots_from_weekly_schedule(profile, target_date)
    → list of (start_time, end_time) tuples for a given date based on
      the doctor's weekly_schedule JSON.  Returns [] if the doctor has
      no schedule for that weekday.

  check_slot_overlap(doctor_user, date, start_time, end_time, exclude_slot_pk=None)
    → True if an active (non-cancelled/no-show) Appointment exists that
      overlaps the proposed time window.  Used before creating/updating slots.

  get_effective_slots_for_date(profile, target_date)
    → Returns a serializer-friendly list of dicts with keys:
        time, end_time, is_available, is_booked, slot_id
      Priority: explicit DoctorAvailableSlot rows → weekly_schedule fallback.
      Booked status is resolved by checking active Appointments.

  dates_for_weekday_in_range(weekday, start_date, weeks_ahead)
    → All dates in [start_date, start_date + weeks_ahead * 7) on that weekday.

NowServing.ph alignment:
  - Slot priority mirrors NowServing: explicit overrides > recurring template.
  - is_booked is computed here so the appointments/views.py available_slots
    action can return a single consistent response shape.

All times are treated as Asia/Manila local time (TIME_ZONE in settings).
"""

from datetime import datetime, time, timedelta, date as date_type
from typing import List, Optional, Tuple

from django.utils import timezone


# Weekday name → Python date.weekday() integer (Monday=0)
_WEEKDAY_MAP = {
    "monday":    0,
    "tuesday":   1,
    "wednesday": 2,
    "thursday":  3,
    "friday":    4,
    "saturday":  5,
    "sunday":    6,
}


def generate_slots_from_weekly_schedule(
    profile,
    target_date: date_type,
) -> List[Tuple[time, time, str]]:
    """
    Given a DoctorProfile and a date, return a list of
    (start_time, end_time, consultation_types) tuples derived from
    profile.weekly_schedule.

    consultation_types is one of: "online", "in_clinic", "both" (default "both").

    Returns an empty list if:
      - weekly_schedule is empty / not set
      - the weekday is not in weekly_schedule
      - the schedule entry is malformed
    """
    schedule: dict = profile.weekly_schedule or {}
    if not schedule:
        return []

    weekday_name = target_date.strftime("%A").lower()  # e.g. "monday"
    day_config = schedule.get(weekday_name)
    if not day_config:
        return []

    try:
        start = datetime.strptime(day_config["start"], "%H:%M").time()
        end   = datetime.strptime(day_config["end"],   "%H:%M").time()
    except (KeyError, ValueError):
        return []

    consult_types = day_config.get("consultation_types", "both")

    slots: List[Tuple[time, time, str]] = []
    current = datetime.combine(target_date, start)
    end_dt  = datetime.combine(target_date, end)

    while current + timedelta(minutes=30) <= end_dt:
        slot_end = current + timedelta(minutes=30)
        slots.append((current.time(), slot_end.time(), consult_types))
        current = slot_end

    return slots


def check_slot_overlap(
    doctor_user,
    target_date: date_type,
    start_time: time,
    end_time: time,
    exclude_slot_pk: Optional[int] = None,
) -> bool:
    """
    Return True if an active Appointment for doctor_user on target_date
    overlaps the [start_time, end_time) window.

    Overlap condition: appointment.time >= start_time AND appointment.time < end_time
    (appointment.time is the start of the 30-min consult slot).

    exclude_slot_pk is unused here (appointments don't reference slots directly)
    but kept for API symmetry with slot-level overlap checks.
    """
    from appointments.models import Appointment

    return Appointment.objects.filter(
        doctor=doctor_user,
        date=target_date,
        time__gte=start_time,
        time__lt=end_time,
    ).exclude(status__in=["cancelled", "no_show"]).exists()


def get_effective_slots_for_date(profile, target_date: date_type) -> List[dict]:
    """
    Return the effective availability for a doctor on a given date as a
    serializer-friendly list of dicts.

    Each dict has:
      {
        "time":               "HH:MM",
        "end_time":           "HH:MM",
        "is_available":       bool,
        "is_booked":          bool,
        "slot_id":            int|None,
        "consultation_types": "online"|"in_clinic"|"both",
      }

    Priority:
      1. Explicit DoctorAvailableSlot rows for this date → use them.
      2. Otherwise → auto-generate from weekly_schedule.
    """
    from appointments.models import Appointment
    from .models import DoctorAvailableSlot

    booked_strs = {
        str(t)[:5]
        for t in Appointment.objects.filter(
            doctor=profile.user,
            date=target_date,
        ).exclude(status__in=["cancelled", "no_show"]).values_list("time", flat=True)
    }

    explicit_qs = DoctorAvailableSlot.objects.filter(
        doctor=profile, date=target_date
    ).order_by("start_time")

    result: List[dict] = []

    if explicit_qs.exists():
        # Derive consultation_types from the day's weekly_schedule entry (if any)
        schedule = profile.weekly_schedule or {}
        weekday_name = target_date.strftime("%A").lower()
        day_config = schedule.get(weekday_name, {})
        day_consult_types = day_config.get("consultation_types", "both")

        for slot in explicit_qs:
            slot_time_str = slot.start_time.strftime("%H:%M")
            is_booked     = slot_time_str in booked_strs
            result.append({
                "time":               slot_time_str,
                "end_time":           slot.end_time.strftime("%H:%M"),
                "is_available":       slot.is_available and not is_booked,
                "is_booked":          is_booked,
                "slot_id":            slot.pk,
                "consultation_types": day_consult_types,
            })
        return result

    # Fall back to weekly_schedule auto-generation
    for start_t, end_t, consult_types in generate_slots_from_weekly_schedule(profile, target_date):
        slot_time_str = start_t.strftime("%H:%M")
        is_booked     = slot_time_str in booked_strs
        result.append({
            "time":               slot_time_str,
            "end_time":           end_t.strftime("%H:%M"),
            "is_available":       not is_booked,
            "is_booked":          is_booked,
            "slot_id":            None,
            "consultation_types": consult_types,
        })

    return result


def dates_for_weekday_in_range(
    weekday: int,
    start_date: date_type,
    weeks_ahead: int,
) -> List[date_type]:
    """
    Return all dates within [start_date, start_date + weeks_ahead * 7)
    that fall on the given weekday (0=Monday … 6=Sunday).

    Used by SlotListCreateView when is_recurring=True to pre-generate
    DoctorAvailableSlot rows for the next N weeks (default 12).
    """
    dates = []
    end_date = start_date + timedelta(weeks=weeks_ahead)
    current = start_date
    while current < end_date:
        if current.weekday() == weekday:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def get_available_weekdays(profile) -> List[str]:
    """
    Return the list of weekday names (lowercase) on which the doctor has
    either a weekly_schedule entry or at least one future explicit slot.

    Used by the frontend to determine which calendar days to enable.
    """
    from .models import DoctorAvailableSlot

    weekdays = set()

    # From weekly_schedule
    schedule = profile.weekly_schedule or {}
    weekdays.update(schedule.keys())

    # From future explicit slots
    today = timezone.localdate()
    future_dates = (
        DoctorAvailableSlot.objects
        .filter(doctor=profile, date__gte=today, is_available=True)
        .values_list("date", flat=True)
        .distinct()
    )
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for d in future_dates:
        weekdays.add(day_names[d.weekday()])

    return sorted(weekdays)
