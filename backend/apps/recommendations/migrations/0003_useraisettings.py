from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0002_aichatmessage_response_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAISettings",
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
                (
                    "mode",
                    models.CharField(
                        choices=[("official", "官方模型"), ("custom", "自定义模型")],
                        default="official",
                        max_length=16,
                        verbose_name="模型来源",
                    ),
                ),
                (
                    "custom_api_base",
                    models.URLField(blank=True, max_length=500, verbose_name="自定义 API 地址"),
                ),
                (
                    "custom_model",
                    models.CharField(blank=True, max_length=200, verbose_name="自定义模型"),
                ),
                (
                    "encrypted_api_key",
                    models.TextField(blank=True, editable=False, verbose_name="加密 API 密钥"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_settings",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="用户",
                    ),
                ),
            ],
            options={
                "verbose_name": "用户 AI 设置",
                "verbose_name_plural": "用户 AI 设置",
            },
        ),
    ]
