from django.contrib import admin
from .models import Device, SensorReading, EnergyRecord, CostSettings, CO2Settings

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
