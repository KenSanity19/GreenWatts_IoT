#!/usr/bin/env python
"""
Quick fix script for GreenWatts IoT performance issues
Run this to fix timezone warnings and optimize database queries
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenwatts.settings')
django.setup()

from django.core.management import call_command
from django.db import connection

def main():
    print("🔧 Starting GreenWatts IoT Quick Fix...")
    
    # Fix timezone issues
    print("\n1. Fixing timezone issues...")
    try:
        call_command('fix_timezones')
        print("✅ Timezone issues fixed")
    except Exception as e:
        print(f"⚠️  Timezone fix error: {e}")
    
    # Create database indexes for better performance
    print("\n2. Optimizing database queries...")
    try:
        with connection.cursor() as cursor:
            # Add index for date-based queries
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_date_year_month 
                ON tbl_sensor_reading (date, EXTRACT(year FROM date), EXTRACT(month FROM date));
            """)
            
            # Add index for device-office queries
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_device_date 
                ON tbl_sensor_reading (device_id, date);
            """)
            
            print("✅ Database indexes created")
    except Exception as e:
        print(f"⚠️  Database optimization error: {e}")
    
    # Update table statistics
    print("\n3. Updating database statistics...")
    try:
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE tbl_sensor_reading;")
            cursor.execute("ANALYZE tbl_device;")
            cursor.execute("ANALYZE tbl_office;")
        print("✅ Database statistics updated")
    except Exception as e:
        print(f"⚠️  Statistics update error: {e}")
    
    print("\n🎉 Quick fix completed!")
    print("\nRecommendations:")
    print("- Restart your Django server to apply timezone changes")
    print("- Monitor query performance for October 2025 filtering")
    print("- Consider adding more specific indexes if performance issues persist")

if __name__ == '__main__':
    main()