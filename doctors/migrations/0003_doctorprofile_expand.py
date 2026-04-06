# Generated migration for doctors app expansion
# Adds new fields to DoctorProfile + creates DoctorHospital, DoctorService, DoctorHMO

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("doctors", "0002_doctorprofile_is_on_demand"),
    ]

    operations = [
        # ── New DoctorProfile fields ──────────────────────────────────────────
        migrations.AddField(
            model_name="doctorprofile",
            name="profile_photo",
            field=models.ImageField(blank=True, null=True, upload_to="doctor_photos/",
                                    help_text="Headshot shown on patient-facing cards."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="bio",
            field=models.TextField(blank=True, help_text="About / professional summary."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="years_of_experience",
            field=models.PositiveIntegerField(blank=True, null=True,
                                              help_text="Years of clinical practice."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="clinic_address",
            field=models.TextField(blank=True, help_text="Full street address of primary clinic."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="city",
            field=models.CharField(blank=True, db_index=True, max_length=100,
                                   help_text="City used for location-based filtering."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="consultation_fee_online",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True,
                                      help_text="Online/video consultation fee in PHP."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="consultation_fee_in_person",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True,
                                      help_text="In-clinic consultation fee in PHP."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="languages_spoken",
            field=models.JSONField(blank=True, default=list,
                                   help_text='e.g. ["Filipino","English","Cebuano"]'),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="sub_specialties",
            field=models.JSONField(blank=True, default=list,
                                   help_text="List of sub-specialty strings."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="is_verified",
            field=models.BooleanField(db_index=True, default=False,
                                      help_text="Admin sets True after PRC license verification."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="last_active_at",
            field=models.DateTimeField(blank=True, null=True,
                                       help_text="Updated by heartbeat ping. Used for Available Now logic."),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        # ── PRC license validator ─────────────────────────────────────────────
        migrations.AlterField(
            model_name="doctorprofile",
            name="prc_license",
            field=models.CharField(
                max_length=20,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        regex=r"^\d{7}$",
                        message="PRC license must be exactly 7 digits.",
                    )
                ],
                help_text="7-digit PRC license number.",
            ),
        ),
        # ── Meta indexes ──────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name="doctorprofile",
            index=models.Index(fields=["specialty", "city"], name="doctor_specialty_city_idx"),
        ),
        migrations.AddIndex(
            model_name="doctorprofile",
            index=models.Index(fields=["is_verified", "invite_accepted"], name="doctor_verified_invite_idx"),
        ),
        # ── DoctorHospital ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="DoctorHospital",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, help_text="Hospital or clinic name.")),
                ("address", models.TextField(blank=True)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("doctor", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="hospitals",
                    to="doctors.doctorprofile",
                )),
            ],
            options={
                "verbose_name": "Doctor Hospital",
                "verbose_name_plural": "Doctor Hospitals",
                "ordering": ["name"],
            },
        ),
        # ── DoctorService ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name="DoctorService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, help_text="Service type offered.")),
                ("doctor", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="services",
                    to="doctors.doctorprofile",
                )),
            ],
            options={
                "verbose_name": "Doctor Service",
                "verbose_name_plural": "Doctor Services",
                "ordering": ["name"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="doctorservice",
            unique_together={("doctor", "name")},
        ),
        # ── DoctorHMO ─────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="DoctorHMO",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, help_text="HMO provider accepted.")),
                ("doctor", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="hmos",
                    to="doctors.doctorprofile",
                )),
            ],
            options={
                "verbose_name": "Doctor HMO",
                "verbose_name_plural": "Doctor HMOs",
                "ordering": ["name"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="doctorhmo",
            unique_together={("doctor", "name")},
        ),
    ]
