"""
Migration 0006: add weekly_schedule to DoctorProfile + create DoctorAvailableSlot.

Data migration note:
  Existing DoctorProfile rows will have weekly_schedule = {} (empty dict, the
  field default).  No data loss — doctors simply have no recurring schedule set
  until they PATCH /doctors/availability/ with their preferred hours.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0005_patienthmo"),
    ]

    operations = [
        # ── 1. Add weekly_schedule to DoctorProfile ───────────────────────────
        migrations.AddField(
            model_name="doctorprofile",
            name="weekly_schedule",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Recurring weekly hours per weekday. "
                    'e.g. {"monday": {"start": "09:00", "end": "17:00"}}. '
                    "Used to auto-generate 30-min slots when no explicit slot rows exist."
                ),
            ),
        ),

        # ── 2. Create DoctorAvailableSlot ─────────────────────────────────────
        migrations.CreateModel(
            name="DoctorAvailableSlot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date",       models.DateField(db_index=True)),
                ("start_time", models.TimeField()),
                ("end_time",   models.TimeField()),
                (
                    "is_available",
                    models.BooleanField(
                        default=True,
                        help_text="False = doctor blocked this slot (e.g. lunch, holiday).",
                    ),
                ),
                (
                    "is_recurring",
                    models.BooleanField(
                        default=False,
                        help_text="True when created from a recurring weekly rule.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="available_slots",
                        to="doctors.doctorprofile",
                    ),
                ),
            ],
            options={
                "verbose_name":        "Doctor Available Slot",
                "verbose_name_plural": "Doctor Available Slots",
                "ordering":            ["date", "start_time"],
            },
        ),

        # ── 3. Unique constraint: one slot per doctor/date/start_time ─────────
        migrations.AlterUniqueTogether(
            name="doctoravailableslot",
            unique_together={("doctor", "date", "start_time")},
        ),

        # ── 4. Composite index for fast date-range queries ────────────────────
        migrations.AddIndex(
            model_name="doctoravailableslot",
            index=models.Index(
                fields=["doctor", "date"],
                name="slot_doctor_date_idx",
            ),
        ),
    ]
