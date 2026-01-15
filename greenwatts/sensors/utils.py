from django.utils import timezone
from django.db import models
from .models import CostSettings, CO2Settings


def get_rates_for_date(target_date):
    """Get cost and CO2 rates that were active on a specific date - optimized"""
    from django.core.cache import cache
    from django.utils import timezone
    
    # Cache key for this specific date
    cache_key = f'rates_for_date_{target_date}'
    cached_rates = cache.get(cache_key)
    if cached_rates:
        return cached_rates
    
    # Convert date to timezone-aware datetime for comparison
    if hasattr(target_date, 'date'):
        target_datetime = target_date
    else:
        target_datetime = timezone.make_aware(timezone.datetime.combine(target_date, timezone.datetime.min.time()))
    
    # Get cost rate for the date
    cost_rate = CostSettings.objects.filter(
        created_at__lte=target_datetime
    ).filter(
        models.Q(ended_at__isnull=True) | models.Q(ended_at__gt=target_datetime)
    ).order_by('-created_at').first()
    
    if not cost_rate:
        cost_rate = CostSettings.get_current_rate()
    
    # Get CO2 rate for the date
    co2_rate = CO2Settings.objects.filter(
        created_at__lte=target_datetime
    ).filter(
        models.Q(ended_at__isnull=True) | models.Q(ended_at__gt=target_datetime)
    ).order_by('-created_at').first()
    
    if not co2_rate:
        co2_rate = CO2Settings.get_current_rate()
    
    rates = {
        'cost_per_kwh': cost_rate.cost_per_kwh if cost_rate else 12.0,
        'co2_emission_factor': co2_rate.co2_emission_factor if co2_rate else 0.475
    }
    
    # Cache the rates for 1 hour
    cache.set(cache_key, rates, 3600)
    return rates


def calculate_energy_metrics_with_historical_rates(sensor_readings):
    """Calculate cost and CO2 emissions using historical rates for each reading - optimized"""
    from django.db import models
    from django.core.cache import cache
    
    total_cost = 0
    total_co2 = 0
    
    # Convert queryset to list to avoid multiple database hits
    if hasattr(sensor_readings, 'values'):
        readings_list = list(sensor_readings.values('date', 'total_energy_kwh'))
    else:
        readings_list = [{'date': r.date, 'total_energy_kwh': r.total_energy_kwh} for r in sensor_readings]
    
    if not readings_list:
        return {'total_cost': 0, 'total_co2': 0}
    
    # Group readings by date to minimize database queries
    readings_by_date = {}
    for reading in readings_list:
        date_key = reading['date']
        energy = reading['total_energy_kwh'] or 0
        if date_key not in readings_by_date:
            readings_by_date[date_key] = 0
        readings_by_date[date_key] += energy
    
    # Cache rates to avoid repeated database queries
    rates_cache = {}
    
    # Calculate metrics for each date using appropriate rates
    for date, total_energy in readings_by_date.items():
        # Use cached rates if available
        cache_key = f'rates_{date}'
        if cache_key in rates_cache:
            rates = rates_cache[cache_key]
        else:
            rates = cache.get(cache_key)
            if rates is None:
                rates = get_rates_for_date(date)
                cache.set(cache_key, rates, 3600)  # Cache for 1 hour
            rates_cache[cache_key] = rates
        
        total_cost += total_energy * rates['cost_per_kwh']
        total_co2 += total_energy * rates['co2_emission_factor']
    
    return {
        'total_cost': total_cost,
        'total_co2': total_co2
    }