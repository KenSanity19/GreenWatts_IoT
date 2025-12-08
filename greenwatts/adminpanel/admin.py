from django.contrib import admin
from .models import Admin, Threshold, ThresholdHistory

admin.site.register(Admin)
admin.site.register(Threshold)

@admin.register(ThresholdHistory)
class ThresholdHistoryAdmin(admin.ModelAdmin):
    list_display = ('history_id', 'energy_efficient_max', 'energy_moderate_max', 'energy_high_max', 
                    'co2_efficient_max', 'co2_moderate_max', 'co2_high_max', 'created_at', 'ended_at')
    list_filter = ('created_at',)
    readonly_fields = ('history_id', 'created_at', 'ended_at')
    ordering = ('-created_at',)
