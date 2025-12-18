# GreenWatts IoT Energy Monitoring System - Complete Formula Reference

## 1. Core Energy Calculations (ESP32)

### Power Calculation
```cpp
float power = voltage * current;  // Watts (W)
```

### Energy Calculation (kWh)
```cpp
// For 10-second reading intervals
float deltaEnergy = power * 10.0 / 3600000.0;  // kWh per reading
// Formula: P(W) × time(s) / (3600 s/h × 1000 W/kW) = kWh

// Daily total energy
float total_energy_kwh = (total_power_sum * reading_interval) / (1000 * 3600);
// Where: reading_interval = 10 seconds
```

### Peak Power Tracking
```cpp
if (power > peakPower) {
    peakPower = power;  // Track maximum power in Watts
}
```

## 2. Environmental Impact Calculations

### Carbon Emissions (CO2)
```python
# Philippines grid emission factor: 0.475 kg CO2/kWh (configurable)
carbon_emission_kgco2 = total_energy_kwh * co2_emission_factor

# ESP32 calculation
totalCarbon += deltaEnergy * 0.475;  // kg CO2
```

### Cost Estimation
```python
# Philippines average rate: 12.0 PHP/kWh (configurable)
cost_estimate = total_energy_kwh * cost_per_kwh

# ESP32 calculation  
totalCost += deltaEnergy * 12.0;  // PHP
```

## 3. Threshold Scaling Formulas

### Time-Based Threshold Scaling
```python
def get_scaled_thresholds(base_thresholds, level):
    scale_factors = {
        'day': 1,
        'week': 7, 
        'month': 30,
        'year': 365
    }
    
    factor = scale_factors.get(level, 1)
    
    return {
        'energy_efficient_max': base_thresholds['energy_efficient_max'] * factor,
        'energy_moderate_max': base_thresholds['energy_moderate_max'] * factor,
        'co2_efficient_max': base_thresholds['co2_efficient_max'] * factor,
        'co2_moderate_max': base_thresholds['co2_moderate_max'] * factor,
    }
```

## 4. Prediction Algorithms

### Monthly CO2 Prediction
```python
# For month: predict based on current month's daily average
days_with_data = current_month_readings.dates('date', 'day').count()
if days_with_data > 0:
    daily_avg = co2_emissions / days_with_data
    predicted_co2 = daily_avg * days_in_month
```

### Cost Prediction
```python
# Predicted cost based on daily average
total_days = (period_end - period_start).days + 1
days_so_far = (so_far_end - period_start).days + 1

if days_so_far > 0 and period_end > now:
    avg_daily = so_far_cost / days_so_far
    predicted_cost = avg_daily * total_days
```

### Energy Usage Prediction
```python
# Default prediction for other levels
predicted_co2 = co2_emissions * 2  // Simple 2x multiplier
```

## 5. Historical Rate Calculations

### Dynamic Rate Application
```python
def get_rates_for_date(target_date):
    # Get cost rate active on specific date
    cost_rate = CostSettings.objects.filter(
        created_at__lte=target_date
    ).filter(
        Q(ended_at__isnull=True) | Q(ended_at__gt=target_date)
    ).order_by('-created_at').first()
    
    # Get CO2 rate active on specific date  
    co2_rate = CO2Settings.objects.filter(
        created_at__lte=target_date
    ).filter(
        Q(ended_at__isnull=True) | Q(ended_at__gt=target_date)
    ).order_by('-created_at').first()
    
    return {
        'cost_per_kwh': cost_rate.cost_per_kwh,
        'co2_emission_factor': co2_rate.co2_emission_factor
    }
```

### Historical Metrics Calculation
```python
def calculate_energy_metrics_with_historical_rates(sensor_readings):
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
```

## 6. Performance Metrics

### Percentage Change Calculation
```python
if prev_cost > 0:
    change_percent = ((current_cost - prev_cost) / prev_cost) * 100
else:
    change_percent = 0

is_decrease = change_percent < 0
change_percent_abs = abs(change_percent)
```

### Office Share Calculation
```python
# Calculate office share percentage
office_share_percentage = (office_energy / total_all_energy * 100) if total_all_energy > 0 else 0
```

### Progress Percentage
```python
# Carbon footprint progress
progress_percentage = (month_so_far_co2 / predicted_co2 * 100) if predicted_co2 > 0 else 0
```

### Savings Calculation
```python
# Estimated savings
savings = prev_cost - predicted_cost if prev_cost > predicted_cost else 0
```

## 7. Status Classification Logic

### Energy Efficiency Status
```python
if total_energy > energy_moderate_max:
    status = 'High'        # Red - Above threshold
elif total_energy > energy_efficient_max:
    status = 'Moderate'    # Yellow - Approaching threshold  
else:
    status = 'Efficient'   # Green - Within limits
```

### Chart Color Coding
```python
colors = []
for energy_value in chart_values:
    if energy_value > energy_moderate_max:
        colors.append('#d9534f')  # Red - High usage
    elif energy_value > energy_efficient_max:
        colors.append('#f0ad4e')  # Yellow - Moderate usage
    else:
        colors.append('#5cb85c')  # Green - Efficient usage
```

## 8. Default Configuration Values

### System Defaults
- **Energy Thresholds**: 10 kWh (efficient), 20 kWh (moderate), 30 kWh (high) - daily basis
- **CO2 Thresholds**: 8 kg (efficient), 13 kg (moderate), 18 kg (high) - daily basis
- **CO2 Emission Factor**: 0.475 kg CO2/kWh (Philippines grid)
- **Cost Rate**: 12.0 PHP/kWh (Philippines average)
- **Reading Interval**: 10 seconds
- **Data Transmission**: Daily at midnight (00:00)

### ESP32 Calculation Constants
```cpp
const unsigned long READ_INTERVAL = 10000; // 10 seconds
const float CO2_FACTOR = 0.475;           // kg CO2/kWh
const float COST_RATE = 12.0;             // PHP/kWh
```

## 9. Data Aggregation Formulas

### Daily Energy Record Creation
```python
# Calculate metrics from sensor readings
total_power_sum = 0
peak_power = 0
reading_interval = 10  # seconds

for reading in sensor_readings:
    power = reading.voltage * reading.current  # Watts
    total_power_sum += power
    peak_power = max(peak_power, power)

# Energy = Power × Time (convert to kWh)
total_energy_kwh = (total_power_sum * reading_interval) / (1000 * 3600)

# Calculate using admin settings
carbon_emission_kgco2 = total_energy_kwh * co2_settings.co2_emission_factor
cost_estimate = total_energy_kwh * cost_settings.cost_per_kwh
```

## 10. Key Mathematical Relationships

### Power-Energy Relationship
```
Energy (kWh) = Power (W) × Time (hours) ÷ 1000
```

### Cost-Energy Relationship
```
Cost (PHP) = Energy (kWh) × Rate (PHP/kWh)
```

### CO2-Energy Relationship
```
CO2 Emissions (kg) = Energy (kWh) × Emission Factor (kg CO2/kWh)
```

### Efficiency Classification
```
Efficient: Energy ≤ Efficient Threshold
Moderate: Efficient Threshold < Energy ≤ Moderate Threshold  
High: Energy > Moderate Threshold
```

---

**Document Version:** 1.0  
**Last Updated:** January 2025  
**Project:** GreenWatts IoT Energy Monitoring System