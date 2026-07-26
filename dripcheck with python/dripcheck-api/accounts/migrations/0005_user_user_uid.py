import uuid
from django.db import migrations, models


def populate_user_uid(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.all():
        user.user_uid = uuid.uuid4()
        user.save(update_fields=['user_uid'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_usertoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='user_uid',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_user_uid, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='user_uid',
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]
