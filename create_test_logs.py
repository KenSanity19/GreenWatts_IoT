#!/usr/bin/env python
import os
import sys
import django
from datetime import datetime, timedelta

# Add the project directory to Python path
sys.path.append('d:/IotProject/GreenWatts_IoT')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenwatts.settings')

django.setup()

from greenwatts.sensors.models import SystemLog, Device
from django.utils import timezone

# Create test system logs
devices = Device.objects.all()[:3]  # Get first 3 devices

if devices:
    for i, device in enumerate(devices):
        # Create different types of logs
        SystemLog.objects.create(
            log_type='data_received',
            device=device,
            message=f'Received 144 sensor readings from device {device.device_id}',
            metadata={'readings_count': 144}
        )
        
        SystemLog.objects.create(
            log_type='spike_detected',
            device=device,
            message=f'Power spike detected: {1500 + i*100}W peak power',
            metadata={'peak_power': 1500 + i*100, 'baseline': 450}
        )
        
        SystemLog.objects.create(
            log_type='device_online',
            device=device,
            message=f'Device {device.device_id} came online',
            timestamp=timezone.now() - timedelta(hours=2)
        )

    print(f"Created test system logs for {len(devices)} devices")
else:
    print("No devices found in database")