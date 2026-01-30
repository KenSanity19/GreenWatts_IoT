from django.core.management.base import BaseCommand
from django.db.models import Sum, Max
from greenwatts.sensors.models import SensorReading, EnergyAggregation, Device
from greenwatts.sensors.utils import calculate_energy_metrics_with_historical_rates
from datetime import date, timedelta
from calendar import monthrange

class Command(BaseCommand):
    help = 'Pre-compute monthly and yearly aggregations for faster queries'

    def handle(self, *args, **options):
        devices = Device.objects.all()
        
        for device in devices:
            # Get date range
            first_reading = SensorReading.objects.filter(device=device).order_by('date').first()
            if not first_reading:
                continue
                
            start_date = first_reading.date
            end_date = date.today()
            
            # Monthly aggregations
            current_year = start_date.year
            current_month = start_date.month
            
            while date(current_year, current_month, 1) <= end_date:
                month_start = date(current_year, current_month, 1)
                _, last_day = monthrange(current_year, current_month)
                month_end = date(current_year, current_month, last_day)
                
                readings = SensorReading.objects.filter(
                    device=device,
                    date__gte=month_start,
                    date__lte=month_end
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
                
                current_month += 1
                if current_month > 12:
                    current_month = 1
                    current_year += 1
            
            # Yearly aggregations
            current_year = start_date.year
            while current_year <= end_date.year:
                year_start = date(current_year, 1, 1)
                year_end = date(current_year, 12, 31)
                
                readings = SensorReading.objects.filter(
                    device=device,
                    date__gte=year_start,
                    date__lte=year_end
                )
                
                if readings.exists():
                    metrics = calculate_energy_metrics_with_historical_rates(readings)
                    agg_data = readings.aggregate(
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
                
                current_year += 1
        
        self.stdout.write(self.style.SUCCESS('Successfully pre-computed aggregations'))