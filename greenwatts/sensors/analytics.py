from django.utils import timezone
from django.db.models import Avg, Max, Count
from datetime import datetime, timedelta
from .models import SensorReading, PowerSpike, WeeklySpikeAnalysis, SystemLog, Device
import statistics

class SpikeAnalyzer:
    def __init__(self, spike_threshold_multiplier=2.0):
        self.spike_threshold_multiplier = spike_threshold_multiplier
    
    def detect_spikes(self, device_id, readings_data):
        """Detect power spikes in real-time sensor data"""
        device = Device.objects.get(device_id=device_id)
        
        # Calculate baseline from recent readings (last 30 readings)
        recent_readings = SensorReading.objects.filter(
            device=device
        ).order_by('-date')[:30]
        
        if recent_readings.count() < 10:
            return []
        
        baseline_powers = [r.voltage * r.current for r in recent_readings]
        baseline_avg = statistics.mean(baseline_powers)
        baseline_std = statistics.stdev(baseline_powers) if len(baseline_powers) > 1 else 0
        
        spike_threshold = baseline_avg + (self.spike_threshold_multiplier * baseline_std)
        
        spikes = []
        for reading in readings_data:
            power = reading['voltage'] * reading['current']
            
            if power > spike_threshold:
                spike = PowerSpike.objects.create(
                    device=device,
                    timestamp=datetime.fromtimestamp(reading['timestamp'], tz=timezone.utc),
                    peak_power=power,
                    baseline_power=baseline_avg,
                    spike_magnitude=power - baseline_avg,
                    duration_seconds=10
                )
                spikes.append(spike)
                
                # Log spike detection
                SystemLog.objects.create(
                    log_type='spike_detected',
                    device=device,
                    message=f"Power spike detected: {power:.2f}W (baseline: {baseline_avg:.2f}W)",
                    metadata={
                        'peak_power': power,
                        'baseline_power': baseline_avg,
                        'spike_magnitude': power - baseline_avg,
                        'threshold': spike_threshold
                    }
                )
        
        return spikes
    
    def generate_weekly_analysis(self, device_id, week_start=None):
        """Generate weekly spike analysis with interpretations"""
        device = Device.objects.get(device_id=device_id)
        
        if not week_start:
            week_start = timezone.now().date() - timedelta(days=7)
        
        week_end = week_start + timedelta(days=6)
        
        # Get spikes for the week
        spikes = PowerSpike.objects.filter(
            device=device,
            timestamp__date__range=[week_start, week_end]
        )
        
        if not spikes.exists():
            interpretation = "No power spikes detected this week. Energy consumption appears stable."
        else:
            spike_count = spikes.count()
            max_spike = spikes.aggregate(Max('peak_power'))['peak_power__max']
            avg_baseline = spikes.aggregate(Avg('baseline_power'))['baseline_power__avg']
            total_duration = spike_count * 10  # Each spike is 10 seconds
            
            # Generate interpretation
            interpretation = self._generate_interpretation(
                spike_count, max_spike, avg_baseline, total_duration
            )
            
            # Calculate spike threshold
            spike_threshold = avg_baseline * self.spike_threshold_multiplier if avg_baseline else 0
        
        # Create or update weekly analysis
        analysis, created = WeeklySpikeAnalysis.objects.update_or_create(
            device=device,
            week_start=week_start,
            defaults={
                'week_end': week_end,
                'spike_count': spike_count if spikes.exists() else 0,
                'max_spike_power': max_spike or 0.0,
                'avg_baseline_power': avg_baseline or 0.0,
                'spike_threshold': spike_threshold if spikes.exists() else 0.0,
                'total_spike_duration_minutes': total_duration // 60 if spikes.exists() else 0,
                'interpretation': interpretation
            }
        )
        
        return analysis
    
    def _generate_interpretation(self, spike_count, max_spike, avg_baseline, total_duration):
        """Generate human-readable interpretation of spike data"""
        interpretations = []
        
        # Spike frequency analysis
        if spike_count == 0:
            interpretations.append("No power spikes detected - excellent energy stability.")
        elif spike_count <= 5:
            interpretations.append(f"Low spike activity ({spike_count} spikes) - normal operation.")
        elif spike_count <= 15:
            interpretations.append(f"Moderate spike activity ({spike_count} spikes) - monitor equipment usage.")
        else:
            interpretations.append(f"High spike activity ({spike_count} spikes) - investigate potential issues.")
        
        # Spike magnitude analysis
        if max_spike and avg_baseline:
            spike_ratio = max_spike / avg_baseline
            if spike_ratio > 3.0:
                interpretations.append(f"Severe power spike detected ({max_spike:.1f}W vs {avg_baseline:.1f}W baseline) - check for equipment malfunctions.")
            elif spike_ratio > 2.0:
                interpretations.append(f"Significant power spike ({max_spike:.1f}W) - review high-power equipment usage.")
            else:
                interpretations.append(f"Minor power variations detected - within acceptable range.")
        
        # Duration analysis
        duration_minutes = total_duration // 60
        if duration_minutes > 60:
            interpretations.append(f"Extended spike duration ({duration_minutes} minutes total) - consider load balancing.")
        elif duration_minutes > 10:
            interpretations.append(f"Moderate spike duration ({duration_minutes} minutes) - normal for equipment startup.")
        
        # Recommendations
        if spike_count > 10:
            interpretations.append("Recommendation: Review equipment schedules and consider staggered startup times.")
        
        return " ".join(interpretations)

class SystemLogger:
    @staticmethod
    def log_data_received(device, readings_count):
        """Log successful data reception"""
        SystemLog.objects.create(
            log_type='data_received',
            device=device,
            message=f"Received {readings_count} sensor readings",
            metadata={'readings_count': readings_count}
        )
    
    @staticmethod
    def log_device_status(device, is_online):
        """Log device online/offline status"""
        log_type = 'device_online' if is_online else 'device_offline'
        message = f"Device {device.device_id} is {'online' if is_online else 'offline'}"
        
        SystemLog.objects.create(
            log_type=log_type,
            device=device,
            message=message,
            metadata={'status': 'online' if is_online else 'offline'}
        )
    
    @staticmethod
    def log_threshold_exceeded(device, metric_type, value, threshold):
        """Log threshold violations"""
        SystemLog.objects.create(
            log_type='threshold_exceeded',
            device=device,
            message=f"{metric_type} threshold exceeded: {value} > {threshold}",
            metadata={
                'metric_type': metric_type,
                'value': value,
                'threshold': threshold
            }
        )
    
    @staticmethod
    def get_24h_logs(device_id=None):
        """Get system logs from last 24 hours"""
        since = timezone.now() - timedelta(hours=24)
        logs = SystemLog.objects.filter(timestamp__gte=since)
        
        if device_id:
            logs = logs.filter(device_id=device_id)
        
        return logs.order_by('-timestamp')