from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_profile"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["email"], name="users_user_email_6f2530_idx"),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["is_admin", "-date_joined"], name="users_user_is_admi_7dabdb_idx"),
        ),
    ]
