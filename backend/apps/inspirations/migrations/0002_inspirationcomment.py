from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inspirations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="InspirationComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField()),
                ("like_count", models.PositiveIntegerField(default=0)),
                ("liked_by", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("inspiration", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="inspirations.inspiration")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="replies", to="inspirations.inspirationcomment")),
                ("reviewer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inspiration_comments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="inspirationcomment",
            index=models.Index(fields=["inspiration", "parent", "created_at"], name="inspiratio_inspir_0654b5_idx"),
        ),
        migrations.AddIndex(
            model_name="inspirationcomment",
            index=models.Index(fields=["reviewer", "-created_at"], name="inspiratio_reviewe_4150dd_idx"),
        ),
        migrations.AddIndex(
            model_name="inspirationcomment",
            index=models.Index(fields=["parent", "created_at"], name="inspiratio_parent__aa5b0a_idx"),
        ),
    ]
