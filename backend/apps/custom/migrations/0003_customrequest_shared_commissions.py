# Generated for shared commission data.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("custom", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customrequest",
            name="type_label",
            field=models.CharField(blank=True, max_length=80, verbose_name="委托类型"),
        ),
        migrations.AddField(
            model_name="customrequest",
            name="budget_note",
            field=models.CharField(blank=True, max_length=80, verbose_name="预算说明"),
        ),
        migrations.AddField(
            model_name="customrequest",
            name="accepted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="接单时间"),
        ),
        migrations.AddField(
            model_name="customrequest",
            name="abandon_requested_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="申请放弃时间"),
        ),
        migrations.AlterField(
            model_name="customrequest",
            name="budget",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="预算数值"),
        ),
        migrations.AlterField(
            model_name="customrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("submitted", "待接单"),
                    ("accepted", "已接单"),
                    ("abandon_requested", "申请放弃中"),
                    ("in_progress", "创作中"),
                    ("reviewing", "待确认"),
                    ("completed", "已完成"),
                    ("cancelled", "已取消"),
                ],
                default="submitted",
                max_length=20,
                verbose_name="状态",
            ),
        ),
    ]
