from django.core.management.base import BaseCommand
from django.utils import timezone
from greenwatts.adminpanel.models import CO2Threshold, EnergyThreshold
from greenwatts.sensors.models import CO2Settings, CostSettings

class Command(BaseCommand):
    help = 'Fix timezone issues in existing data'

    def handle(self, *args, **options):
        self.stdout.write('Fixing timezone issues...')
        
        # Fix CO2Threshold ended_at fields
        co2_thresholds = CO2Threshold.objects.filter(ended_at__isnull=False)
        for threshold in co2_thresholds:
            if threshold.ended_at and timezone.is_naive(threshold.ended_at):
                threshold.ended_at = timezone.make_aware(threshold.ended_at)
                threshold.save()
        
        # Fix EnergyThreshold ended_at fields  
        energy_thresholds = EnergyThreshold.objects.filter(ended_at__isnull=False)
        for threshold in energy_thresholds:
            if threshold.ended_at and timezone.is_naive(threshold.ended_at):
                threshold.ended_at = timezone.make_aware(threshold.ended_at)
                threshold.save()
        
        # Fix CO2Settings ended_at fields
        co2_settings = CO2Settings.objects.filter(ended_at__isnull=False)
        for setting in co2_settings:
            if setting.ended_at and timezone.is_naive(setting.ended_at):
                setting.ended_at = timezone.make_aware(setting.ended_at)
                setting.save()
        
        # Fix CostSettings ended_at fields
        cost_settings = CostSettings.objects.filter(ended_at__isnull=False)
        for setting in cost_settings:
            if setting.ended_at and timezone.is_naive(setting.ended_at):
                setting.ended_at = timezone.make_aware(setting.ended_at)
                setting.save()
        
        self.stdout.write(self.style.SUCCESS('Successfully fixed timezone issues'))