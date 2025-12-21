from django.core.management.base import BaseCommand
from django.utils import timezone
from greenwatts.sensors.models import Device
from greenwatts.sensors.analytics import SpikeAnalyzer

class Command(BaseCommand):
    help = 'Generate weekly spike analysis for all devices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--device-id',
            type=int,
            help='Analyze specific device only',
        )

    def handle(self, *args, **options):
        analyzer = SpikeAnalyzer()
        
        if options['device_id']:
            devices = Device.objects.filter(device_id=options['device_id'])
        else:
            devices = Device.objects.filter(status='Active')
        
        for device in devices:
            try:
                analysis = analyzer.generate_weekly_analysis(device.device_id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Generated analysis for Device {device.device_id}: '
                        f'{analysis.spike_count} spikes detected'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error analyzing Device {device.device_id}: {str(e)}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Analysis complete for {devices.count()} devices')
        )