#!/usr/bin/env python
"""
Performance optimization script for date filtering
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenwatts.settings')
django.setup()

from django.db import connection

def add_performance_indexes():
    """Add additional indexes for better performance"""
    print("Adding performance indexes...")
    
    with connection.cursor() as cursor:
        # Add composite index for date filtering
        cursor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_date_device_composite 
            ON tbl_sensor_reading(date DESC, device_id);
        """)
        print("Added composite index for sensor readings")
        
        # Add partial index for active settings
        cursor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cost_settings_active 
            ON tbl_cost_settings(created_at) 
            WHERE ended_at IS NULL;
        """)
        print("Added partial index for active cost settings")
        
        cursor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_co2_settings_active 
            ON tbl_co2_settings(created_at) 
            WHERE ended_at IS NULL;
        """)
        print("Added partial index for active CO2 settings")
        
        # Add index for office filtering
        cursor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_office_name_exclude 
            ON tbl_office(office_id) 
            WHERE name != 'DS';
        """)
        print("Added index for office filtering")

def analyze_tables():
    """Update table statistics for better query planning"""
    print("Updating table statistics...")
    
    with connection.cursor() as cursor:
        tables = ['tbl_sensor_reading', 'tbl_cost_settings', 'tbl_co2_settings', 'tbl_device', 'tbl_office']
        for table in tables:
            cursor.execute(f"ANALYZE {table};")
            print(f"Analyzed {table}")

if __name__ == "__main__":
    try:
        add_performance_indexes()
        analyze_tables()
        print("Performance optimization completed successfully!")
    except Exception as e:
        print(f"Error during optimization: {e}")