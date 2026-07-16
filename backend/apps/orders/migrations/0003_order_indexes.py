from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["buyer", "-created_at"], name="orders_orde_buyer_i_67c51b_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["seller", "-created_at"], name="orders_orde_seller__c9231f_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["artwork", "-created_at"], name="orders_orde_artwork_85c3c6_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["status", "-created_at"], name="orders_orde_status_079368_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["-created_at"], name="orders_orde_created_f0ce29_idx"),
        ),
    ]
