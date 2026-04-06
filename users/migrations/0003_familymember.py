from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_alter_user_birthdate_alter_user_phone"),
    ]

    operations = [
        migrations.CreateModel(
            name="FamilyMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("age", models.PositiveSmallIntegerField()),
                ("gender", models.CharField(
                    choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
                    max_length=10,
                )),
                ("relationship", models.CharField(
                    choices=[
                        ("spouse",  "Spouse"),
                        ("child",   "Child"),
                        ("parent",  "Parent"),
                        ("sibling", "Sibling"),
                        ("other",   "Other"),
                    ],
                    default="other",
                    max_length=10,
                )),
                ("birthdate", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("patient", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="family_members",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["name"]},
        ),
    ]
