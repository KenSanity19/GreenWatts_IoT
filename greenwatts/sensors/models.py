from django.db import models
from django.utils import timezone

from greenwatts.users.models import Office

class Device(models.Model):
    device_id = models.AutoField(primary_key=True)
    appliance_type = models.CharField(max_length=100, null=True, blank=True)
    installed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, default="Active")
    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="devices", null=True, blank=True)

    class Meta:
        db_table = "tbl_device"

    def __str__(self):
        return self.appliance_type if self.appliance_type else f"Device {self.device_id}"

class SensorReading(models.Model):
    """
    Stores individual sensor readings from ESP32.
    Each reading contains voltage and current at a specific timestamp.
    """
    reading_id = models.AutoField(primary_key=True)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="sensor_readings")
    voltage = models.FloatField()  # Voltage in Volts
    current = models.FloatField()  # Current in Amperes
    date = models.DateField()  # When the reading was taken

    class Meta:
        db_table = "tbl_sensor_reading"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['device', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Reading {self.reading_id} - Device {self.device.device_id} - {self.date}"


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
