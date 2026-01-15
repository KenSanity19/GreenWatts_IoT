#!/usr/bin/env python
"""
Database optimization script for GreenWatts IoT
Run this to optimize database queries and add missing indexes
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenwatts.settings')
django.setup()

from django.db import connection
from django.core.management import execute_from_command_line

def create_indexes():
    """Create database indexes to optimize query performance"""
    
    with connection.cursor() as cursor:
        print("Creating optimized database indexes...")
        
        # Index for date-based queries on SensorReading
        try:
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_date_device 
                ON tbl_sensor_reading (date, device_id);
            """)
            print("✓ Created index on (date, device_id)")
        except Exception as e:
            print(f"Index on (date, device_id) already exists or error: {e}")
        
        # Index for office-based queries
        try:
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_office_date 
                ON tbl_sensor_reading (device_id, date) 
                WHERE device_id IN (
                    SELECT device_id FROM tbl_device 
                    WHERE office_id IS NOT NULL
                );
            """)
            print("✓ Created partial index for office queries")
        except Exception as e:
            print(f"Office index already exists or error: {e}")
        
        # Index for year/month queries
        try:
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_reading_year_month 
                ON tbl_sensor_reading (EXTRACT(year FROM date), EXTRACT(month FROM date), device_id);
            """)
            print("✓ Created index for year/month queries")
        except Exception as e:
            print(f"Year/month index already exists or error: {e}")
        
        # Index for device office relationship
        try:
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_device_office 
                ON tbl_device (office_id) WHERE office_id IS NOT NULL;
            """)
            print("✓ Created index on device office relationship")
        except Exception as e:
            print(f"Device office index already exists or error: {e}")
        
        print("Database optimization completed!")

def analyze_tables():
    """Analyze tables to update statistics"""
    with connection.cursor() as cursor:
        print("Analyzing tables to update statistics...")
        cursor.execute("ANALYZE tbl_sensor_reading;")
        cursor.execute("ANALYZE tbl_device;")
        cursor.execute("ANALYZE tbl_office;")
        print("✓ Table analysis completed")

if __name__ == '__main__':
    print("Starting database optimization...")
    create_indexes()
    analyze_tables()
    print("Optimization complete!")