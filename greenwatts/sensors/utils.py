from django.utils import timezone
from django.db import models
from .models import CostSettings, CO2Settings


def get_rates_for_date(target_date):
    """Get cost and CO2 rates that were active on a specific date"""
    
    # Get cost rate for the date
    cost_rate = CostSettings.objects.filter(
        created_at__lte=target_date
    ).filter(
        models.Q(ended_at__isnull=True) | models.Q(ended_at__gt=target_date)
    ).order_by('-created_at').first()
    
    if not cost_rate:
        cost_rate = CostSettings.objects.create()
    
    # Get CO2 rate for the date
    co2_rate = CO2Settings.objects.filter(
        created_at__lte=target_date
    ).filter(
        models.Q(ended_at__isnull=True) | models.Q(ended_at__gt=target_date)
    ).order_by('-created_at').first()
    
    if not co2_rate:
        co2_rate = CO2Settings.objects.create()
    
    return {
        'cost_per_kwh': cost_rate.cost_per_kwh,
        'co2_emission_factor': co2_rate.co2_emission_factor
    }


def calculate_energy_metrics_with_historical_rates(sensor_readings):
    """Calculate cost and CO2 emissions using historical rates for each reading"""
    from django.db import models
    
    total_cost = 0
    total_co2 = 0
    
    # Group readings by date to minimize database queries
    readings_by_date = {}
    for reading in sensor_readings:
        date_key = reading.date
        if date_key not in readings_by_date:
            readings_by_date[date_key] = []
        readings_by_date[date_key].append(reading)
    
    # Calculate metrics for each date using appropriate rates
    for date, readings in readings_by_date.items():
        rates = get_rates_for_date(date)
        
        for reading in readings:
            energy = reading.total_energy_kwh or 0
            total_cost += energy * rates['cost_per_kwh']
            total_co2 += energy * rates['co2_emission_factor']
    
    return {
        'total_cost': total_cost,
        'total_co2': total_co2
    }