from django.conf import settings
from django.db import migrations, models


def migrate_comment_likes(apps, schema_editor):
    InspirationComment = apps.get_model("inspirations", "InspirationComment")
    User = apps.get_model("users", "User")

    users_by_username = {
        user.username: user.pk
        for user in User.objects.only("id", "username")
    }

    for comment in InspirationComment.objects.only("id", "liked_by", "like_count").iterator(chunk_size=500):
        usernames = list(dict.fromkeys(comment.liked_by or []))
        user_ids = [users_by_username[username] for username in usernames if username in users_by_username]
        if user_ids:
            comment.liked_users.add(*user_ids)
        if comment.like_count != len(user_ids) or comment.liked_by != usernames:
            comment.liked_by = usernames
            comment.like_count = len(user_ids)
            comment.save(update_fields=["liked_by", "like_count"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inspirations", "0003_rename_inspiratio_inspir_0654b5_idx_inspiration_inspira_2037fc_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="inspirationcomment",
            name="liked_users",
            field=models.ManyToManyField(blank=True, related_name="liked_inspiration_comments", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(migrate_comment_likes, migrations.RunPython.noop),
    ]
