import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("piquano_admin_center", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeamPermission",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "team_id",
                    models.UUIDField(
                        verbose_name="Team",
                        help_text="UUID des Teams (FK ohne DB-Constraint, da Team in consumer-App lebt)",
                    ),
                ),
                ("is_granted", models.BooleanField(default=True, verbose_name="Erteilt")),
                ("granted_at", models.DateTimeField(auto_now_add=True, verbose_name="Erteilt am")),
                (
                    "granted_by",
                    models.CharField(blank=True, max_length=150, verbose_name="Erteilt von"),
                ),
                (
                    "permission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_assignments",
                        to="piquano_admin_center.permission",
                        verbose_name="Berechtigung",
                    ),
                ),
            ],
            options={
                "verbose_name": "Team-Berechtigung",
                "verbose_name_plural": "Team-Berechtigungen",
                "db_table": "piquano_admin_center_teampermission",
                "ordering": ["team_id", "permission"],
                "unique_together": {("team_id", "permission")},
            },
        ),
    ]
