from django.core.management.base import BaseCommand
from django.db.models import Sum, Max
from greenwatts.sensors.models import SensorReading, EnergyAggregation, Device
from greenwatts.sensors.utils import calculate_energy_metrics_with_historical_rates
from datetime import date, timedelta
from calendar import monthrange

class Command(BaseCommand):
    help = 'Update aggregations incrementally'

    def handle(self, *args, **options):
        devices = Device.objects.all()
        today = date.today()
        
        for device in devices:
            # Update current month only
            month_start = today.replace(day=1)
            _, last_day = monthrange(today.year, today.month)
            month_end = date(today.year, today.month, last_day)
            
            readings = SensorReading.objects.filter(
                device=device,
                date__gte=month_start,
                date__lte=min(month_end, today)
            )
            
            if readings.exists():
                metrics = calculate_energy_metrics_with_historical_rates(readings)
                agg_data = readings.aggregate(
                    total_energy=Sum('total_energy_kwh'),
                    peak_power=Max('peak_power_w')
                )
                
                EnergyAggregation.objects.update_or_create(
                    device=device,
                    date=month_start,
                    period_type='monthly',
                    defaults={
                        'total_energy_kwh': agg_data['total_energy'] or 0,
                        'peak_power_w': agg_data['peak_power'] or 0,
                        'total_cost': metrics['total_cost'],
                        'total_co2': metrics['total_co2']
                    }
                )
            
            # Update current year only
            year_start = date(today.year, 1, 1)
            year_readings = SensorReading.objects.filter(
                device=device,
                date__gte=year_start,
                date__lte=today
            )
            
            if year_readings.exists():
                metrics = calculate_energy_metrics_with_historical_rates(year_readings)
                agg_data = year_readings.aggregate(
                    total_energy=Sum('total_energy_kwh'),
                    peak_power=Max('peak_power_w')
                )
                
                EnergyAggregation.objects.update_or_create(
                    device=device,
                    date=year_start,
                    period_type='yearly',
                    defaults={
                        'total_energy_kwh': agg_data['total_energy'] or 0,
                        'peak_power_w': agg_data['peak_power'] or 0,
                        'total_cost': metrics['total_cost'],
                        'total_co2': metrics['total_co2']
                    }
                )
        
        self.stdout.write(self.style.SUCCESS('Updated current aggregations'))