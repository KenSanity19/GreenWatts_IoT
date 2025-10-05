from django.db import models

from greenwatts.adminpanel.models import Office

class Device(models.Model):
    device_id = models.AutoField(primary_key=True)
    # Additional fields can be added here as needed, e.g. device name, type, etc.
    installed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, default="active")
    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="devices", null=True, blank=True)

    class Meta:
        db_table = "tbl_device"

    def __str__(self):
        return self.name if self.name else f"Device {self.device_id}"

class EnergyRecord(models.Model):
    record_id = models.AutoField(primary_key=True)
    date = models.DateField()
    total_energy_kWh = models.FloatField()
    peak_power_W = models.FloatField()
    carbon_emission_kgCO2 = models.FloatField()
    cost_estimate = models.FloatField()
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    class Meta:
        db_table = "tbl_energy_record"

    def __str__(self):
        return f"EnergyRecord {self.record_id} for Device {self.device.device_id}"
