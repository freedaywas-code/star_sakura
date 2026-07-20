import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0005_review_liked_users"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="replies",
                to="reviews.review",
                verbose_name="父评价",
            ),
        ),
        migrations.AddIndex(
            model_name="review",
            index=models.Index(
                fields=["artwork", "parent", "created_at"],
                name="reviews_art_parent_created_idx",
            ),
        ),
    ]
