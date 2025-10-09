from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='office',
            name='admin',
            field=models.ForeignKey(
                default=1,  # You may need to adjust this default or make it nullable if no admin with id=1 exists
                on_delete=django.db.models.deletion.CASCADE,
                related_name='offices',
                to='adminpanel.admin',
            ),
            preserve_default=False,
        ),
    ]
