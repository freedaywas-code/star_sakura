from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="aichatmessage",
            name="response_mode",
            field=models.CharField(
                blank=True,
                choices=[("ai", "AI"), ("local", "本地"), ("fallback", "降级")],
                default="",
                max_length=16,
                verbose_name="回复模式",
            ),
        ),
    ]
