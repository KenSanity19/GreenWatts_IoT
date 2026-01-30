from django.db import models
from .models import Device

class EnergyAggregation(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    date = models.DateField()
    period_type = models.CharField(max_length=10, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'), 
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly')
    ])
    total_energy_kwh = models.FloatField(default=0)
    peak_power_w = models.FloatField(default=0)
    total_cost = models.FloatField(default=0)
    total_co2 = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "tbl_energy_aggregation"
        unique_together = ['device', 'date', 'period_type']
        indexes = [
            models.Index(fields=['device', 'period_type', 'date']),
            models.Index(fields=['period_type', 'date']),
        ]