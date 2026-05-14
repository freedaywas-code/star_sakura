from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("artworks", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="artwork",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="artworks/%Y/%m/", verbose_name="画作图片"),
        ),
    ]
