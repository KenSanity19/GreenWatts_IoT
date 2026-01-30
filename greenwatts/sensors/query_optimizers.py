from django.db import models
from django.core.cache import cache
from .models import SensorReading, EnergyAggregation
from django.db.models import Sum, Max
from datetime import date, timedelta

class QueryOptimizer:
    @staticmethod
    def get_fast_aggregated_data(devices, filter_kwargs, level='day'):
        """Ultra-fast aggregation using pre-computed data"""
        cache_key = f"fast_agg_{hash(str(devices.values_list('device_id', flat=True)))}{hash(str(filter_kwargs))}{level}"
        cached = cache.get(cache_key)
        if cached:
            return cached
            
        # Try pre-computed aggregations first
        if level in ['monthly', 'yearly']:
            period_type = level.rstrip('ly')  # 'monthly' -> 'month'
            agg_data = EnergyAggregation.objects.filter(
                device__in=devices,
                period_type=period_type,
                **_convert_filter_for_aggregation(filter_kwargs, level)
            ).aggregate(
                total_energy=Sum('total_energy_kwh'),
                peak_power=Max('peak_power_w'),
                total_cost=Sum('total_cost'),
                total_co2=Sum('total_co2')
            )
            
            if agg_data['total_energy']:
                cache.set(cache_key, agg_data, 600)  # 10 min cache
                return agg_data
        
        # Fallback to raw data with minimal fields
        result = SensorReading.objects.filter(
            device__in=devices, **filter_kwargs
        ).aggregate(
            total_energy=Sum('total_energy_kwh'),
            peak_power=Max('peak_power_w')
        )
        result.update({'total_cost': 0, 'total_co2': 0})
        
        cache.set(cache_key, result, 300)
        return result

def _convert_filter_for_aggregation(filter_kwargs, level):
    """Convert date filters for aggregation table"""
    if 'date__year' in filter_kwargs and 'date__month' in filter_kwargs:
        return {'date': date(filter_kwargs['date__year'], filter_kwargs['date__month'], 1)}
    elif 'date__year' in filter_kwargs:
        return {'date': date(filter_kwargs['date__year'], 1, 1)}
    return filter_kwargs