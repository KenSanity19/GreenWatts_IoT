from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control
from django.http import HttpResponse, JsonResponse
from django.db import models
from ..adminpanel.models import EnergyThreshold, CO2Threshold, Notification
from ..adminpanel.utils import get_scaled_thresholds
from ..sensors.models import SensorReading, CostSettings, CO2Settings
import csv

def get_unread_notifications_count(office):
    """Helper function to get unread notifications count for an office"""
    return Notification.objects.filter(
        models.Q(target_office=office) | models.Q(is_global=True),
        is_read=False
    ).count()

def get_base_thresholds():
    """Get base (daily) threshold values"""
    energy_threshold = EnergyThreshold.objects.filter(ended_at__isnull=True).first()
    co2_threshold = CO2Threshold.objects.filter(ended_at__isnull=True).first()
    
    return {
        'energy_efficient_max': energy_threshold.efficient_max if energy_threshold else 10.0,
        'energy_moderate_max': energy_threshold.moderate_max if energy_threshold else 20.0,
        'co2_efficient_max': co2_threshold.efficient_max if co2_threshold else 8.0,
        'co2_moderate_max': co2_threshold.moderate_max if co2_threshold else 13.0,
    }

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def index(request):
    from ..adminpanel.login_attempts import is_locked_out, record_failed_attempt, clear_attempts, get_lockout_time_remaining
    from .two_factor import get_device_fingerprint, is_trusted_device, send_otp
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if is_locked_out(username, 'user'):
            messages.error(request, "Account locked. Try again in 5 minutes.")
            return render(request, 'index.html')
        
        try:
            from .models import Office
            office = Office.objects.get(username=username)
            user = auth.authenticate(username=username, password=password)
            if user is not None:
                clear_attempts(username, 'user')

                # Check device fingerprint for 2FA
                device_fingerprint = get_device_fingerprint(request)
                
                if is_trusted_device(username, device_fingerprint):
                    # Trusted device - login directly
                    auth.login(request, user)
                    return redirect('users:dashboard')
                else:
                    # New device - require 2FA
                    if send_otp(username, office.email):
                        request.session['pending_2fa_user'] = username
                        request.session['device_fingerprint'] = device_fingerprint
                        return redirect('users:verify_otp')
                    else:
                        messages.error(request, 'Failed to send verification code. Please try again.')
            else:
                attempts = record_failed_attempt(username, 'user')
                if attempts >= 5:
                    messages.error(request, 'Account locked for 5 minutes due to multiple failed attempts.')
                elif attempts >= 2:
                    remaining = 5 - attempts
                    messages.error(request, f'Invalid password. {remaining} attempts remaining.')
                else:
                    messages.error(request, 'Invalid password')
        except Office.DoesNotExist:
            attempts = record_failed_attempt(username, 'user')
            if attempts >= 5:
                messages.error(request, 'Account locked for 5 minutes due to multiple failed attempts.')
            elif attempts >= 2:
                remaining = 5 - attempts
                messages.error(request, f'User does not exist. {remaining} attempts remaining.')
            else:
                messages.error(request, 'User does not exist')
            return redirect('users:index')
    return render(request, 'index.html')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def dashboard(request):
    from django.db.models import Sum, Max
    from django.db.models.functions import ExtractYear, ExtractMonth
    from django.utils import timezone
    from datetime import timedelta, date
    from calendar import monthrange
    import json
    from datetime import datetime as dt

    office = request.user
    devices = office.devices.all()
    
    # Get unread notifications count and notifications data
    unread_notifications_count = get_unread_notifications_count(office)
    
    # Get notifications for modal
    admin_notifications = Notification.objects.filter(
        models.Q(target_office=office) | models.Q(is_global=True)
    ).order_by('-created_at')[:10]
    
    notifications = []
    for notif in admin_notifications:
        notifications.append({
            'title': notif.title,
            'message': notif.message,
            'type': notif.notification_type,
            'timestamp': notif.created_at
        })
    
    # Get current rates
    cost_rate = CostSettings.get_current_rate().cost_per_kwh
    co2_rate = CO2Settings.get_current_rate().co2_emission_factor
    
    # Get selected day, month, year from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    
    # Force month filtering when month is selected
    if selected_month and not selected_day:
        if not selected_year:
            selected_year = str(dt.now().year)
    
    # Year options: all years with data for this office
    years_with_data = SensorReading.objects.filter(
        device__in=devices
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    year_options = [str(y) for y in years_with_data]
    
    # Month options: all months with data for this office
    months_with_data = SensorReading.objects.filter(
        device__in=devices
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')

    
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    month_options = [{'value': str(m), 'name': month_names[m-1]} for m in months_with_data]
    
    # Day options: all days with data, or filtered by month/year if selected
    if selected_month and selected_year:
        day_options = [d.strftime('%m/%d/%Y') for d in SensorReading.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__in=devices
        ).dates('date', 'day').order_by('-date')]
    else:
        day_options = [d.strftime('%m/%d/%Y') for d in SensorReading.objects.filter(
            device__in=devices
        ).dates('date', 'day').order_by('-date')]

    # Get latest date for Day dropdown display (latest in current filter context)
    latest_day_display = day_options[0] if day_options else None
    
    # Determine filter kwargs and level
    filter_kwargs = {}
    selected_date = None
    level = 'day'
    
    if selected_day:
        try:
            month_str, day_str, year_str = selected_day.split('/')
            selected_date = date(int(year_str), int(month_str), int(day_str))
            filter_kwargs = {'date': selected_date}
            level = 'day'
            selected_month = month_str
            selected_year = year_str
        except ValueError:
            selected_date = None
    elif selected_month and selected_year:
        filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
        level = 'month'
    elif selected_year:
        filter_kwargs = {'date__year': int(selected_year)}
        level = 'month'
    else:
        # Default to latest date
        latest_data = SensorReading.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
        latest_date = latest_data['latest_date']
        if latest_date:
            filter_kwargs = {'date': latest_date}
            selected_date = latest_date
            selected_day = latest_date.strftime('%m/%d/%Y')
            selected_month = str(latest_date.month)
            selected_year = str(latest_date.year)
            level = 'day'

    # Total energy usage for selected filter
    energy_usage = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0

    # Cost predicted for selected filter (calculated from energy)
    cost_predicted = energy_usage * cost_rate

    # CO2 emissions for selected filter (calculated from energy)
    co2_emissions = energy_usage * co2_rate

    # Active alerts: Show overall computation as single entry with scaled thresholds
    base_thresholds = get_base_thresholds()
    scaled_thresholds = get_scaled_thresholds(base_thresholds, level)
    
    if energy_usage > scaled_thresholds['energy_moderate_max']:
        status = 'High'
    elif energy_usage > scaled_thresholds['energy_efficient_max']:
        status = 'Moderate'
    else:
        status = 'Efficient'
    active_alerts = [{
        'office_name': office.name,
        'energy_usage': energy_usage,
        'status': status
    }]

    # Change in cost data - filter consistently based on level
    if level == 'month':
        # Compare current month with previous month
        current_year = int(selected_year)
        current_month = int(selected_month)
        prev_year = current_year
        prev_month = current_month - 1
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        
        current_energy = SensorReading.objects.filter(
            date__year=current_year, date__month=current_month,
            device__in=devices
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
        
        prev_energy = SensorReading.objects.filter(
            date__year=prev_year, date__month=prev_month,
            device__in=devices
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
        
        current_cost = current_energy * cost_rate
        prev_cost = prev_energy * cost_rate
        
        bar1_label = date(prev_year, prev_month, 1).strftime('%B %Y')
        bar2_label = date(current_year, current_month, 1).strftime('%B %Y')
    elif selected_date:
        # Compare selected_date and previous day
        previous_date = selected_date - timedelta(days=1)
        current_energy = SensorReading.objects.filter(
            date=selected_date, device__in=devices
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
        prev_energy = SensorReading.objects.filter(
            date=previous_date, device__in=devices
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
        
        current_cost = current_energy * cost_rate
        prev_cost = prev_energy * cost_rate
        
        bar1_label = previous_date.strftime('%B %d')
        bar2_label = selected_date.strftime('%B %d')
    else:
        # Default to last two days with data
        change_dates_qs = SensorReading.objects.filter(
            device__in=devices
        ).dates('date', 'day').distinct().order_by('-date')[:2]
        change_dates = list(change_dates_qs)
        if len(change_dates) >= 2:
            current_energy = SensorReading.objects.filter(
                date=change_dates[0], device__in=devices
            ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
            prev_energy = SensorReading.objects.filter(
                date=change_dates[1], device__in=devices
            ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
            
            current_cost = current_energy * cost_rate
            prev_cost = prev_energy * cost_rate
            
            bar1_label = change_dates[1].strftime('%B %d')
            bar2_label = change_dates[0].strftime('%B %d')
        else:
            current_cost = prev_cost = 0
            bar1_label = bar2_label = 'N/A'
    
    if prev_cost > 0:
        change_percent = ((current_cost - prev_cost) / prev_cost) * 100
    else:
        change_percent = 0
    is_decrease = change_percent < 0
    change_percent_abs = round(min(abs(change_percent), 100), 2)
    max_cost = max(current_cost, prev_cost) if current_cost > 0 or prev_cost > 0 else 1
    heights = [(prev_cost / max_cost * 100) if max_cost > 0 else 0, (current_cost / max_cost * 100) if max_cost > 0 else 0]
    change_data = {
        'bar1_label': bar1_label,
        'bar1_height': heights[0],
        'bar2_label': bar2_label,
        'bar2_height': heights[1],
        'percent': change_percent_abs,
        'type': 'DECREASE' if is_decrease else 'INCREASE',
        'arrow': 'down' if is_decrease else 'up',
        'color_class': 'decrease' if is_decrease else 'increase'
    }

    # Carbon footprint calculation based on level
    if level == 'month':
        # For month: predict based on current month's daily average
        current_year = int(selected_year)
        current_month = int(selected_month)
        from calendar import monthrange
        _, days_in_month = monthrange(current_year, current_month)
        
        # Get days with data so far in the month
        days_with_data = SensorReading.objects.filter(
            date__year=current_year, date__month=current_month,
            device__in=devices
        ).dates('date', 'day').count()
        
        if days_with_data > 0:
            daily_avg = co2_emissions / days_with_data
            predicted_co2 = daily_avg * days_in_month
        else:
            predicted_co2 = co2_emissions
        
        month_so_far_co2 = co2_emissions
        predicted_date = date(current_year, current_month, days_in_month)
    else:
        # Default prediction for other levels
        predicted_co2 = co2_emissions * 2
        month_so_far_co2 = co2_emissions
        if selected_date:
            predicted_date = selected_date + timedelta(days=7)
        else:
            predicted_date = timezone.now().date() + timedelta(days=7)
    
    # Calculate progress percentage for carbon footprint bar
    progress_percentage = (month_so_far_co2 / predicted_co2 * 100) if predicted_co2 > 0 else 0

    context = {
        'office': office,
        'selected_date': selected_date,
        'predicted_date': predicted_date,
        'day_options': day_options,
        'month_options': month_options,
        'year_options': year_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'latest_day_display': latest_day_display,
        'level': level,
        'energy_usage': f"{energy_usage:.2f}",
        'cost_predicted': f"₱{cost_predicted:.2f}",
        'co2_emissions': f"{co2_emissions:.2f}",
        'active_alerts': active_alerts,
        'change_data': change_data,
        'month_so_far_co2': f"{month_so_far_co2:.2f}",
        'predicted_co2': f"{predicted_co2:.2f}",
        'progress_percentage': f"{progress_percentage:.1f}",
        'unread_notifications_count': unread_notifications_count,
        'notifications': notifications,
    }

    return render(request, 'users/dashboard.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def notifications(request):
    office = request.user
    
    # Get unread notifications count before marking as read
    unread_notifications_count = get_unread_notifications_count(office)
    
    # Get admin notifications for this office
    admin_notifications = Notification.objects.filter(
        models.Q(target_office=office) | models.Q(is_global=True)
    ).order_by('-created_at')[:10]
    
    # Mark notifications as read when user visits notifications page
    Notification.objects.filter(
        models.Q(target_office=office) | models.Q(is_global=True),
        is_read=False
    ).update(is_read=True)
    
    # Convert to list format
    notifications = []
    for notif in admin_notifications:
        notifications.append({
            'title': notif.title,
            'message': notif.message,
            'type': notif.notification_type,
            'timestamp': notif.created_at
        })
    
    context = {
        'office': office,
        'notifications': notifications,
        'unread_notifications_count': 0  # Set to 0 since we just marked all as read
    }
    
    return render(request, 'users/notifications.html', context)

# Additional functions will be added in separate files due to length constraints