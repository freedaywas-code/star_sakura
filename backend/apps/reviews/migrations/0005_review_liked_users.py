from django.conf import settings
from django.db import migrations, models


def migrate_review_likes(apps, schema_editor):
    Review = apps.get_model("reviews", "Review")
    User = apps.get_model("users", "User")

    users_by_username = {
        user.username: user.pk
        for user in User.objects.only("id", "username")
    }

    for review in Review.objects.only("id", "liked_by", "like_count").iterator(chunk_size=500):
        usernames = list(dict.fromkeys(review.liked_by or []))
        user_ids = [users_by_username[username] for username in usernames if username in users_by_username]
        if user_ids:
            review.liked_users.add(*user_ids)
        if review.like_count != len(user_ids) or review.liked_by != usernames:
            review.liked_by = usernames
            review.like_count = len(user_ids)
            review.save(update_fields=["liked_by", "like_count"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reviews", "0004_review_reviews_rev_artwork_4d7b98_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="liked_users",
            field=models.ManyToManyField(blank=True, related_name="liked_reviews", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(migrate_review_likes, migrations.RunPython.noop),
    ]
