# Generated migration for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminpanel', '0009_wifinetwork'),
    ]

    operations = [
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_energy_threshold_ended_at ON tbl_energy_threshold(ended_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_energy_threshold_ended_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_co2_threshold_ended_at ON tbl_co2_threshold(ended_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_co2_threshold_ended_at;"
        ),
    ]