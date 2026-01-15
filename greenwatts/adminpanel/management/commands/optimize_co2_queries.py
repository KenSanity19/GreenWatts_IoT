from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Optimize database indexes for CO2 emission queries'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Add composite indexes for better performance
            try:
                # Index for date + office filtering
                cursor.execute("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_date_office 
                    ON tbl_sensor_reading (date, device_id) 
                    INCLUDE (total_energy_kwh);
                """)
                self.stdout.write('Created index: idx_sensor_reading_date_office')
                
                # Index for year/month filtering
                cursor.execute("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_year_month 
                    ON tbl_sensor_reading (EXTRACT(year FROM date), EXTRACT(month FROM date), device_id) 
                    INCLUDE (total_energy_kwh);
                """)
                self.stdout.write('Created index: idx_sensor_reading_year_month')
                
                # Index for device + office join optimization
                cursor.execute("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_device_office_active 
                    ON tbl_device (office_id) 
                    WHERE status = 'Active';
                """)
                self.stdout.write('Created index: idx_device_office_active')
                
                # Partial index for non-DS offices
                cursor.execute("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_office_non_ds 
                    ON tbl_office (office_id) 
                    WHERE name != 'DS';
                """)
                self.stdout.write('Created index: idx_office_non_ds')
                
                self.stdout.write(self.style.SUCCESS('Successfully optimized CO2 query indexes'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error creating indexes: {e}'))