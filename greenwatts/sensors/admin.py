from django.contrib import admin
from .models import Device, SensorReading, EnergyRecord, CostSettings, CO2Settings, SystemLog, WeeklySpikeAnalysis, PowerSpike

@admin.register(CostSettings)
class CostSettingsAdmin(admin.ModelAdmin):
    list_display = ['cost_per_kwh', 'created_at', 'ended_at']
    fields = ['cost_per_kwh']
    
    def has_add_permission(self, request):
        return not CostSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(CO2Settings)
class CO2SettingsAdmin(admin.ModelAdmin):
    list_display = ['co2_emission_factor', 'created_at', 'ended_at']
    fields = ['co2_emission_factor']
    
    def has_add_permission(self, request):
        return not CO2Settings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['device_id', 'appliance_type', 'status', 'office']
    list_filter = ['status', 'office']

@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ['reading_id', 'device', 'date', 'voltage', 'current', 'total_energy_kwh', 'peak_power_w']
    list_filter = ['date', 'device']
    readonly_fields = ['reading_id']

@admin.register(EnergyRecord)
class EnergyRecordAdmin(admin.ModelAdmin):
    list_display = ['record_id', 'device', 'date', 'total_energy_kwh', 'peak_power_w', 'carbon_emission_kgco2', 'cost_estimate']
    list_filter = ['date', 'device']
    readonly_fields = ['record_id']

@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'log_type', 'device', 'message']
    list_filter = ['log_type', 'timestamp', 'device']
    readonly_fields = ['log_id', 'timestamp']
    search_fields = ['message']

@admin.register(WeeklySpikeAnalysis)
class WeeklySpikeAnalysisAdmin(admin.ModelAdmin):
    list_display = ['device', 'week_start', 'spike_count', 'max_spike_power', 'created_at']
    list_filter = ['week_start', 'device']
    readonly_fields = ['analysis_id', 'created_at']
    search_fields = ['interpretation']

@admin.register(PowerSpike)
class PowerSpikeAdmin(admin.ModelAdmin):
    list_display = ['device', 'timestamp', 'peak_power', 'baseline_power', 'spike_magnitude']
    list_filter = ['timestamp', 'device']
    readonly_fields = ['spike_id', 'detected_at']
