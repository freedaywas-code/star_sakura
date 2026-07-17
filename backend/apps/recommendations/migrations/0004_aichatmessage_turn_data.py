from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0003_useraisettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="aichatmessage",
            name="turn_data",
            field=models.JSONField(blank=True, default=dict, verbose_name="结构化轮次数据"),
        ),
    ]
