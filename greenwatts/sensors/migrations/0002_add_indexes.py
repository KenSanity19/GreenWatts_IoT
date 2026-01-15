# Generated migration for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sensors', '0010_powerspike_systemlog_weeklyspikeanalysis'),
    ]

    operations = [
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_cost_settings_ended_at ON tbl_cost_settings(ended_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_cost_settings_ended_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_co2_settings_ended_at ON tbl_co2_settings(ended_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_co2_settings_ended_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_sensor_reading_date_device ON tbl_sensor_reading(date, device_id);",
            reverse_sql="DROP INDEX IF EXISTS idx_sensor_reading_date_device;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_sensor_reading_date_month_year ON tbl_sensor_reading(EXTRACT(year FROM date), EXTRACT(month FROM date));",
            reverse_sql="DROP INDEX IF EXISTS idx_sensor_reading_date_month_year;"
        ),
    ]