from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Max, Sum
import json
from datetime import datetime, timedelta
from .models import Device, SensorReading, EnergyRecord, CostSettings, CO2Settings
from greenwatts.adminpanel.models import WiFiNetwork

def index(request):
    return HttpResponse("Hello from Sensors app")

@csrf_exempt
@require_http_methods(["GET"])
def get_wifi_networks(request):
    """
    API endpoint for ESP32 to fetch WiFi networks from admin settings.
    Returns active WiFi networks ordered by priority.
    """
    try:
        wifi_networks = WiFiNetwork.objects.filter(is_active=True).order_by('priority', 'ssid')
        
        networks_data = []
        for network in wifi_networks:
            networks_data.append({
                "ssid": network.ssid,
                "password": network.password,
                "priority": network.priority
            })
        
        return JsonResponse({
            "status": "success",
            "networks": networks_data,
            "count": len(networks_data)
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def receive_sensor_data(request):
    """
    API endpoint to receive daily batch sensor data from ESP32 devices.

    Expected JSON payload for daily batch:
    {
        "device_id": 1,
        "reading_count": 8640,
        "readings": [
            {
                "voltage": 230.5,
                "current": 2.45,
                "timestamp": 1698345600
            },
            ...
        ]
    }
    """
    try:
        data = json.loads(request.body)

        device_id = data.get("device_id")
        reading_count = data.get("reading_count", 0)
        readings = data.get("readings", [])

        # Validate required fields
        if not device_id:
            return JsonResponse({
                "status": "error",
                "message": "Missing required field: device_id"
            }, status=400)

        # Verify device exists
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": f"Device with ID {device_id} not found"
            }, status=404)

        # Handle batch readings (from daily collection)
        if readings and len(readings) > 0:
            return _process_batch_readings(device, readings, reading_count)

        # Handle single reading (for backward compatibility)
        voltage = data.get("voltage")
        current = data.get("current")
        timestamp = data.get("timestamp")

        if voltage is None or current is None:
            return JsonResponse({
                "status": "error",
                "message": "Missing required fields: voltage, current"
            }, status=400)

        # Store single reading
        dt = datetime.fromtimestamp(timestamp or 0, tz=timezone.utc) if timestamp else timezone.now()

        power = voltage * current
        sensor_reading = SensorReading.objects.create(
            device=device,
            date=dt.date(),
            voltage=voltage,
            current=current,
            total_energy_kwh=0.0,  # Will be calculated later
            peak_power_w=power
        )

        print(f"[{datetime.now()}] Device {device_id} - Voltage: {voltage}V, Current: {current}A")

        return JsonResponse({
            "status": "success",
            "message": "Sensor data received successfully",
            "device_id": device_id,
            "voltage": voltage,
            "current": current
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


def _process_batch_readings(device, readings, reading_count):
    """
    Process batch readings from daily collection.
    Store individual readings and calculate daily aggregate.
    """
    try:
        print(f"[{datetime.now()}] Processing {reading_count} readings for Device {device.device_id}")

        # Create SensorReading objects
        sensor_readings = []
        for reading in readings:
            try:
                voltage = reading.get("voltage")
                current = reading.get("current")
                timestamp = reading.get("timestamp")

                # Validate reading data
                if voltage is None or current is None or timestamp is None:
                    continue

                # Convert Unix timestamp to datetime
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

                power = voltage * current
                sensor_reading = SensorReading(
                    device=device,
                    date=dt.date(),
                    voltage=voltage,
                    current=current,
                    total_energy_kwh=0.0,
                    peak_power_w=power
                )
                sensor_readings.append(sensor_reading)
            except (ValueError, TypeError) as e:
                print(f"Error processing reading: {e}")
                continue

        # Bulk create for efficiency
        if sensor_readings:
            created_readings = SensorReading.objects.bulk_create(sensor_readings)
            print(f"Stored {len(created_readings)} readings in database")

            # Calculate daily aggregate
            _calculate_daily_aggregate(device, sensor_readings)

        return JsonResponse({
            "status": "success",
            "message": f"Received and stored {len(sensor_readings)} readings",
            "device_id": device.device_id,
            "readings_stored": len(sensor_readings)
        }, status=200)

    except Exception as e:
        print(f"Error processing batch readings: {e}")
        return JsonResponse({
            "status": "error",
            "message": f"Error processing readings: {str(e)}"
        }, status=500)


def _calculate_daily_aggregate(device, sensor_readings):
    """
    Calculate daily energy metrics from sensor readings.
    """
    try:
        if not sensor_readings:
            return

        # Get the date from the first reading
        first_reading = sensor_readings[0]
        reading_date = first_reading.timestamp.date()

        # Calculate metrics
        total_power_sum = 0
        peak_power = 0
        reading_interval = 10  # seconds

        for reading in sensor_readings:
            power = reading.voltage * reading.current  # Watts
            total_power_sum += power
            peak_power = max(peak_power, power)

        # Energy = Power × Time (convert to kWh)
        # Total power sum is in watts, multiply by interval (10s) and convert to hours
        total_energy_kwh = (total_power_sum * reading_interval) / (1000 * 3600)

        # Get current settings
        cost_settings = CostSettings.get_current_rate()
        co2_settings = CO2Settings.get_current_rate()
        
        # Calculate using admin settings
        carbon_emission_kgco2 = total_energy_kwh * co2_settings.co2_emission_factor
        cost_estimate = total_energy_kwh * cost_settings.cost_per_kwh

        # Update or create daily record
        energy_record, created = EnergyRecord.objects.update_or_create(
            device=device,
            date=reading_date,
            defaults={
                'total_energy_kwh': total_energy_kwh,
                'peak_power_w': peak_power,
                'carbon_emission_kgco2': carbon_emission_kgco2,
                'cost_estimate': cost_estimate,
            }
        )

        action = "Created" if created else "Updated"
        print(f"{action} EnergyRecord for Device {device.device_id} on {reading_date}")
        print(f"  Energy: {total_energy_kwh:.2f} kWh")
        print(f"  Peak Power: {peak_power:.2f} W")
        print(f"  Emissions: {carbon_emission_kgco2:.2f} kg CO2")
        print(f"  Cost: {cost_estimate:.2f} PHP")

    except Exception as e:
        print(f"Error calculating daily aggregate: {e}")
