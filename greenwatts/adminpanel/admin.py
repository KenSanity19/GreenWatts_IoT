from django.contrib import admin
from .models import Admin, EnergyThreshold, CO2Threshold, WiFiNetwork

admin.site.register(Admin)

@admin.register(WiFiNetwork)
class WiFiNetworkAdmin(admin.ModelAdmin):
    list_display = ('wifi_id', 'ssid', 'priority', 'is_active', 'created_at')
    list_filter = ('is_active', 'priority')
    search_fields = ('ssid',)
    ordering = ('priority', 'ssid')

@admin.register(EnergyThreshold)
class EnergyThresholdAdmin(admin.ModelAdmin):
    list_display = ('threshold_id', 'efficient_max', 'moderate_max', 'high_max', 'created_at', 'ended_at')
    list_filter = ('created_at',)
    readonly_fields = ('threshold_id', 'created_at', 'ended_at')
    ordering = ('-created_at',)

@admin.register(CO2Threshold)
class CO2ThresholdAdmin(admin.ModelAdmin):
    list_display = ('threshold_id', 'efficient_max', 'moderate_max', 'high_max', 'created_at', 'ended_at')
    list_filter = ('created_at',)
    readonly_fields = ('threshold_id', 'created_at', 'ended_at')
    ordering = ('-created_at',)
