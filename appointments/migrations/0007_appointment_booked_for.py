from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Adds booked-for-other fields to Appointment.

    NowServing.ph pattern: the logged-in patient (booker) remains the
    `patient` FK for payment/notifications. These new fields capture the
    actual consultee when booking on behalf of a family member.

    Depends on users.0003_familymember so the FK target exists first.
    """

    dependencies = [
        # Both 0006 migrations exist; depend on the later one alphabetically
        ("appointments", "0006_appointment_consult_notes_and_more"),
        ("users",        "0003_familymember"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="family_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="appointments",
                to="users.familymember",
                help_text="Saved family member this appointment is for (optional).",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="booked_for_name",
            field=models.CharField(
                blank=True,
                max_length=200,
                help_text="Full name of the person being seen (if not the booker).",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="booked_for_age",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text="Age of the person being seen.",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="booked_for_gender",
            field=models.CharField(
                blank=True,
                max_length=10,
                choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="booked_for_relationship",
            field=models.CharField(
                blank=True,
                max_length=10,
                choices=[
                    ("self",    "Self"),
                    ("spouse",  "Spouse"),
                    ("child",   "Child"),
                    ("parent",  "Parent"),
                    ("sibling", "Sibling"),
                    ("other",   "Other"),
                ],
                default="self",
            ),
        ),
    ]
