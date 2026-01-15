#!/usr/bin/env python
"""
Quick fix for CO2 emission page performance issues
Run this script to optimize database queries and add caching
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenwatts.settings')
django.setup()

from django.db import connection
from django.core.cache import cache

def optimize_database():
    """Add database indexes for better query performance"""
    print("Optimizing database indexes...")
    
    with connection.cursor() as cursor:
        try:
            # Check if indexes exist before creating
            cursor.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'tbl_sensor_reading' 
                AND indexname = 'idx_sensor_reading_date_office_opt';
            """)
            
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE INDEX CONCURRENTLY idx_sensor_reading_date_office_opt 
                    ON tbl_sensor_reading (date, device_id) 
                    INCLUDE (total_energy_kwh);
                """)
                print("✓ Created index: idx_sensor_reading_date_office_opt")
            else:
                print("✓ Index already exists: idx_sensor_reading_date_office_opt")
                
            # Add year/month index for filtering
            cursor.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'tbl_sensor_reading' 
                AND indexname = 'idx_sensor_reading_year_month_opt';
            """)
            
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE INDEX CONCURRENTLY idx_sensor_reading_year_month_opt 
                    ON tbl_sensor_reading (
                        EXTRACT(year FROM date), 
                        EXTRACT(month FROM date), 
                        device_id
                    ) INCLUDE (total_energy_kwh);
                """)
                print("✓ Created index: idx_sensor_reading_year_month_opt")
            else:
                print("✓ Index already exists: idx_sensor_reading_year_month_opt")
                
        except Exception as e:
            print(f"✗ Error creating indexes: {e}")

def clear_cache():
    """Clear existing cache to ensure fresh data"""
    print("Clearing cache...")
    try:
        cache.clear()
        print("✓ Cache cleared successfully")
    except Exception as e:
        print(f"✗ Error clearing cache: {e}")

def analyze_tables():
    """Update table statistics for better query planning"""
    print("Updating table statistics...")
    
    with connection.cursor() as cursor:
        try:
            cursor.execute("ANALYZE tbl_sensor_reading;")
            cursor.execute("ANALYZE tbl_device;")
            cursor.execute("ANALYZE tbl_office;")
            print("✓ Table statistics updated")
        except Exception as e:
            print(f"✗ Error analyzing tables: {e}")

def main():
    print("🚀 Starting CO2 Emission Page Performance Optimization...")
    print("=" * 60)
    
    # Step 1: Clear cache
    clear_cache()
    
    # Step 2: Optimize database
    optimize_database()
    
    # Step 3: Update statistics
    analyze_tables()
    
    print("=" * 60)
    print("✅ Optimization complete!")
    print("\nThe CO2 emission page should now load faster when filtering December 2025.")
    print("If you still experience slow loading, consider:")
    print("1. Reducing the date range being queried")
    print("2. Adding more specific filters")
    print("3. Checking server resources (CPU/Memory)")

if __name__ == "__main__":
    main()