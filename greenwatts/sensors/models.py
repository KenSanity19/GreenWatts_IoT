from django.db import models
from django.utils import timezone

from greenwatts.users.models import Office

class Device(models.Model):
    device_id = models.AutoField(primary_key=True)
    # Additional fields can be added here as needed, e.g. device name, type, etc.
    installed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, default="Active")
    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="devices", null=True, blank=True)

    class Meta:
        db_table = "tbl_device"

    def __str__(self):
        return self.name if self.name else f"Device {self.device_id}"

class SensorReading(models.Model):
    """
    Stores individual sensor readings from ESP32.
    Each reading contains voltage and current at a specific timestamp.
    """
    reading_id = models.AutoField(primary_key=True)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="sensor_readings")
    voltage = models.FloatField()  # Voltage in Volts
    current = models.FloatField()  # Current in Amperes
    timestamp = models.DateTimeField()  # When the reading was taken
    created_at = models.DateTimeField(auto_now_add=True)  # When it was stored in DB

    class Meta:
        db_table = "tbl_sensor_reading"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device', 'timestamp']),
            models.Index(fields=['device', 'created_at']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"Reading {self.reading_id} - Device {self.device.device_id} - {self.timestamp}"


class EnergyRecord(models.Model):
    record_id = models.AutoField(primary_key=True)
    date = models.DateField()
    total_energy_kwh = models.FloatField()
    peak_power_w = models.FloatField()
    carbon_emission_kgco2 = models.FloatField()
    cost_estimate = models.FloatField()
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    class Meta:
        db_table = "tbl_energy_record"

    def __str__(self):
        return f"EnergyRecord {self.record_id} for Device {self.device.device_id}"
