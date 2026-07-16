from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="reviews/%Y/%m/", verbose_name="评价图片"),
        ),
        migrations.AddField(
            model_name="review",
            name="like_count",
            field=models.PositiveIntegerField(default=0, verbose_name="点赞数"),
        ),
        migrations.AddField(
            model_name="review",
            name="liked_by",
            field=models.JSONField(blank=True, default=list, verbose_name="点赞用户"),
        ),
    ]
