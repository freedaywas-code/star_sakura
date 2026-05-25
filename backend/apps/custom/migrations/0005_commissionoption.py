# Generated manually on 2026-05-25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("custom", "0004_customrequest_custom_cust_status_fcd9b6_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommissionOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=40, unique=True, verbose_name="选项代码")),
                ("title", models.CharField(max_length=80, verbose_name="委托类型")),
                ("price_label", models.CharField(blank=True, max_length=80, verbose_name="价格说明")),
                ("sort_order", models.PositiveSmallIntegerField(default=0, verbose_name="排序")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
            options={
                "verbose_name": "委托类型",
                "verbose_name_plural": "委托类型",
                "ordering": ["sort_order", "id"],
                "indexes": [models.Index(fields=["is_active", "sort_order"], name="custom_comm_is_acti_3d8e2b_idx")],
            },
        ),
    ]
