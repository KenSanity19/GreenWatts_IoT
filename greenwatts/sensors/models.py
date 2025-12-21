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
    reading_id = models.AutoField(primary_key=True)
    date = models.DateField() 
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="sensor_readings")
    voltage = models.FloatField()  # Voltage in Volts
    current = models.FloatField()  # Current in Amperes
    total_energy_kwh = models.FloatField(default=0.0)
    peak_power_w = models.FloatField(default=0.0)

    class Meta:
        db_table = "tbl_sensor_reading"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['device', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Reading {self.reading_id} - Device {self.device.device_id} - {self.date}"


class CostSettings(models.Model):
    cost_id = models.AutoField(primary_key=True)
    cost_per_kwh = models.FloatField(default=12.0)  # PHP per kWh
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tbl_cost_settings"

    def __str__(self):
        return f"Cost: {self.cost_per_kwh} PHP/kWh"

    @classmethod
    def get_current_rate(cls):
        return cls.objects.filter(ended_at__isnull=True).first() or cls.objects.create()


class CO2Settings(models.Model):
    co2_id = models.AutoField(primary_key=True)
    co2_emission_factor = models.FloatField(default=0.475)  # kg CO2 per kWh
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tbl_co2_settings"

    def __str__(self):
        return f"CO2: {self.co2_emission_factor} kg/kWh"

    @classmethod
    def get_current_rate(cls):
        return cls.objects.filter(ended_at__isnull=True).first() or cls.objects.create()


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


class SystemLog(models.Model):
    LOG_TYPES = [
        ('data_received', 'Data Received'),
        ('device_offline', 'Device Offline'),
        ('device_online', 'Device Online'),
        ('threshold_exceeded', 'Threshold Exceeded'),
        ('system_error', 'System Error'),
        ('spike_detected', 'Spike Detected'),
    ]
    
    log_id = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    log_type = models.CharField(max_length=20, choices=LOG_TYPES)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "tbl_system_log"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'log_type']),
            models.Index(fields=['device', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.log_type} - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"


class WeeklySpikeAnalysis(models.Model):
    analysis_id = models.AutoField(primary_key=True)
    week_start = models.DateField()
    week_end = models.DateField()
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    spike_count = models.IntegerField(default=0)
    max_spike_power = models.FloatField(default=0.0)
    avg_baseline_power = models.FloatField(default=0.0)
    spike_threshold = models.FloatField(default=0.0)
    total_spike_duration_minutes = models.IntegerField(default=0)
    interpretation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_weekly_spike_analysis"
        ordering = ['-week_start']
        unique_together = ['week_start', 'device']

    def __str__(self):
        return f"Spike Analysis - Device {self.device.device_id} - Week {self.week_start}"


class PowerSpike(models.Model):
    spike_id = models.AutoField(primary_key=True)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    peak_power = models.FloatField()
    baseline_power = models.FloatField()
    spike_magnitude = models.FloatField()  # peak_power - baseline_power
    duration_seconds = models.IntegerField(default=10)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_power_spike"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"Spike {self.spike_id} - {self.peak_power}W at {self.timestamp}"
