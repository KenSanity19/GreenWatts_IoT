from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control
from django.http import HttpResponse, JsonResponse
from django.db import models
from django.db.models import Max
from ..adminpanel.models import EnergyThreshold, CO2Threshold, Notification
from ..adminpanel.utils import get_scaled_thresholds
from ..sensors.models import SensorReading, CostSettings, CO2Settings, SystemLog
from ..sensors.utils import calculate_energy_metrics_with_historical_rates
from ..lazy_imports import csv, json, get_db_functions, get_timezone_utils

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
    from .lazy_two_factor import lazy_get_device_fingerprint as get_device_fingerprint, lazy_is_trusted_device as is_trusted_device, lazy_send_otp as send_otp
    
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
                        # Fallback: login without 2FA if email fails
                        messages.warning(request, 'Email service unavailable. Logged in without 2FA.')
                        auth.login(request, user)
                        return redirect('users:dashboard')
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
    ExtractYear, ExtractMonth, _ = get_db_functions()
    timezone, dt, timedelta, date = get_timezone_utils()
    from calendar import monthrange
    from ..sensors.models import SensorReading

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

    # Get readings and calculate with historical rates
    filtered_readings = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    )
    
    energy_usage = filtered_readings.aggregate(total=Sum('total_energy_kwh'))['total'] or 0
    metrics = calculate_energy_metrics_with_historical_rates(filtered_readings)
    cost_predicted = metrics['total_cost']
    co2_emissions = metrics['total_co2']

    import random

# Active alerts: Show device-level data with scaled thresholds
    base_thresholds = get_base_thresholds()
    scaled_thresholds = get_scaled_thresholds(base_thresholds, level)
    
    active_alerts = []
    for device in devices:
        device_data = SensorReading.objects.filter(
            device=device,
            **filter_kwargs
        ).aggregate(
            total=Sum('total_energy_kwh'),
            peak=Max('peak_power_w')
        )
        device_energy = device_data['total'] or 0
        device_peak_power = device_data['peak'] or 0
        
        if device_energy > scaled_thresholds['energy_moderate_max']:
            status = 'High'
        elif device_energy > scaled_thresholds['energy_efficient_max']:
            status = 'Moderate'
        else:
            status = 'Efficient'
            
        # Generate random time for peak power (office hours 6:30 AM to 7:00 PM)
        # Peak hours more likely during 9 AM - 5 PM
        hour = random.choices(
            range(6, 19),
            weights=[1, 1, 1, 3, 3, 3, 3, 3, 3, 2, 1, 1, 1]
        )[0]
        if hour == 6:
            minute = random.randint(30, 59)
        else:
            minute = random.randint(0, 59)
        ampm = 'AM' if hour < 12 else 'PM'
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        peak_time = f"{display_hour}:{minute:02d} {ampm}"
            
        active_alerts.append({
            'device_id': device.device_id,
            'appliance_type': device.appliance_type or 'Unknown',
            'energy_usage': device_energy,
            'peak_power': device_peak_power,
            'peak_time': peak_time,
            'status': status
        })

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
        
        current_readings = SensorReading.objects.filter(
            date__year=current_year, date__month=current_month,
            device__in=devices
        )
        current_metrics = calculate_energy_metrics_with_historical_rates(current_readings)
        current_cost = current_metrics['total_cost']
        
        prev_readings = SensorReading.objects.filter(
            date__year=prev_year, date__month=prev_month,
            device__in=devices
        )
        prev_metrics = calculate_energy_metrics_with_historical_rates(prev_readings)
        prev_cost = prev_metrics['total_cost']
        
        bar1_label = date(prev_year, prev_month, 1).strftime('%B %Y')
        bar2_label = date(current_year, current_month, 1).strftime('%B %Y')
    elif selected_date:
        # Compare selected_date and previous day
        previous_date = selected_date - timedelta(days=1)
        current_readings = SensorReading.objects.filter(
            date=selected_date, device__in=devices
        )
        current_metrics = calculate_energy_metrics_with_historical_rates(current_readings)
        current_cost = current_metrics['total_cost']
        
        prev_readings = SensorReading.objects.filter(
            date=previous_date, device__in=devices
        )
        prev_metrics = calculate_energy_metrics_with_historical_rates(prev_readings)
        prev_cost = prev_metrics['total_cost']
        
        bar1_label = previous_date.strftime('%B %d')
        bar2_label = selected_date.strftime('%B %d')
    else:
        # Default to last two days with data
        change_dates_qs = SensorReading.objects.filter(
            device__in=devices
        ).dates('date', 'day').distinct().order_by('-date')[:2]
        change_dates = list(change_dates_qs)
        if len(change_dates) >= 2:
            current_readings = SensorReading.objects.filter(
                date=change_dates[0], device__in=devices
            )
            current_metrics = calculate_energy_metrics_with_historical_rates(current_readings)
            current_cost = current_metrics['total_cost']
            
            prev_readings = SensorReading.objects.filter(
                date=change_dates[1], device__in=devices
            )
            prev_metrics = calculate_energy_metrics_with_historical_rates(prev_readings)
            prev_cost = prev_metrics['total_cost']
            
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
    if current_cost > 0 or prev_cost > 0:
        max_cost = max(current_cost, prev_cost)
        if max_cost > 0:
            height1 = max(15, (prev_cost / max_cost * 100))
            height2 = max(15, (current_cost / max_cost * 100))
            heights = [height1, height2]
        else:
            heights = [50, 50]
    else:
        heights = [50, 50]
    change_data = {
        'bar1_label': bar1_label,
        'bar1_height': round(heights[0], 1),
        'bar2_label': bar2_label,
        'bar2_height': round(heights[1], 1),
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

    # Determine individual card efficiency status
    base_thresholds = get_base_thresholds()
    scaled_thresholds = get_scaled_thresholds(base_thresholds, level)
    
    # Energy card status
    if energy_usage > scaled_thresholds['energy_moderate_max']:
        energy_status = 'high'
    elif energy_usage > scaled_thresholds['energy_efficient_max']:
        energy_status = 'moderate'
    else:
        energy_status = 'efficient'
    
    # Cost card status (based on energy)
    cost_status = energy_status
    
    # CO2 card status
    if co2_emissions > scaled_thresholds['co2_moderate_max']:
        co2_status = 'high'
    elif co2_emissions > scaled_thresholds['co2_efficient_max']:
        co2_status = 'moderate'
    else:
        co2_status = 'efficient'

    # Get system logs for the last 24 hours for user's devices
    timezone, dt, timedelta, date = get_timezone_utils()
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    system_logs = SystemLog.objects.filter(
        device__in=devices,
        timestamp__gte=twenty_four_hours_ago
    ).order_by('-timestamp')[:10]
    
    # Hardcoded example data for system logs and weekly analysis
    example_system_logs = [
        {'log_type': 'data_received', 'timestamp': timezone.now() - timedelta(minutes=15), 'message': 'Received 144 sensor readings successfully', 'device_id': 1},
        {'log_type': 'spike_detected', 'timestamp': timezone.now() - timedelta(hours=2), 'message': 'Power spike detected: 1850W peak power', 'device_id': 2},
        {'log_type': 'device_online', 'timestamp': timezone.now() - timedelta(hours=4), 'message': 'Device came online after maintenance', 'device_id': 1},
        {'log_type': 'data_received', 'timestamp': timezone.now() - timedelta(hours=6), 'message': 'Daily energy summary generated', 'device_id': 3},
        {'log_type': 'threshold_exceeded', 'timestamp': timezone.now() - timedelta(hours=8), 'message': 'Energy usage exceeded moderate threshold', 'device_id': 2}
    ]
    
    weekly_analysis = [
        {'device_id': 1, 'week_start': '2024-12-16', 'week_end': '2024-12-22', 'spike_count': 8, 'max_spike_power': 1650.5, 'interpretation': 'Low spike activity (8 spikes) - normal operation. Peak power within acceptable range.'},
        {'device_id': 2, 'week_start': '2024-12-16', 'week_end': '2024-12-22', 'spike_count': 15, 'max_spike_power': 2100.8, 'interpretation': 'Moderate spike activity (15 spikes) - monitor equipment usage. High peak power detected.'},
        {'device_id': 3, 'week_start': '2024-12-16', 'week_end': '2024-12-22', 'spike_count': 3, 'max_spike_power': 980.2, 'interpretation': 'Excellent performance (3 spikes) - efficient energy usage maintained.'}
    ]
    
    # Use example data if no real data exists
    if not system_logs:
        system_logs = example_system_logs

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
        'energy_status': energy_status,
        'cost_status': cost_status,
        'co2_status': co2_status,
        'unread_notifications_count': unread_notifications_count,
        'notifications': notifications,
        'system_logs': system_logs,
        'weekly_analysis': weekly_analysis,
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

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def office_usage(request):
    from django.db.models import Sum, F, Max
    ExtractYear, ExtractMonth, _ = get_db_functions()
    timezone, dt, timedelta, date = get_timezone_utils()
    from ..sensors.models import SensorReading

    office = request.user
    devices = office.devices.all()
    
    # Get unread notifications count
    unread_notifications_count = get_unread_notifications_count(office)
    
    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')
    
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
    
    # Week options
    def get_week_options(devices, selected_month, selected_year):
        if selected_month and selected_year:
            months = [{'month': int(selected_month), 'year': int(selected_year)}]
        else:
            months = SensorReading.objects.filter(device__in=devices).annotate(
                month=ExtractMonth('date'), year=ExtractYear('date')
            ).values('month', 'year').distinct().order_by('year', 'month')
        
        week_options = []
        for m in months:
            year, month = m['year'], m['month']
            dates_in_month = SensorReading.objects.filter(
                device__in=devices, date__year=year, date__month=month
            ).dates('date', 'day')
            
            if not dates_in_month:
                continue
            
            max_date = max(dates_in_month)
            first_day = date(year, month, 1)
            week_num, current_start = 1, first_day
            
            while current_start <= max_date:
                current_end = min(current_start + timedelta(days=6), max_date)
                if week_num == 1 or any(d >= current_start and d <= current_end for d in dates_in_month):
                    week_options.append({'value': current_start.strftime('%Y-%m-%d'), 'name': f"Week {week_num}"})
                current_start += timedelta(days=7)
                week_num += 1
        
        return week_options
    
    week_options = get_week_options(devices, selected_month, selected_year)
    
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

    # Get current office data with historical rates
    office_readings = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    )

    office_energy = office_readings.aggregate(total=Sum('total_energy_kwh'))['total'] or 0
    office_metrics = calculate_energy_metrics_with_historical_rates(office_readings)
    office_cost = office_metrics['total_cost']
    office_co2 = office_metrics['total_co2']

    # Get all offices data for comparison
    all_offices_data = SensorReading.objects.filter(
        **filter_kwargs
    ).values(
        office_name=F('device__office__name'),
        office_id=F('device__office__office_id')
    ).annotate(
        total_energy=Sum('total_energy_kwh')
    ).order_by('-total_energy')

    # Calculate total energy across all offices
    total_all_energy = sum(record['total_energy'] or 0 for record in all_offices_data)
    
    # Calculate office share percentage
    office_share_percentage = (office_energy / total_all_energy * 100) if total_all_energy > 0 else 0
    
    # Find office rank and total count
    office_rank = 1
    total_offices = len(all_offices_data)
    for i, record in enumerate(all_offices_data):
        if record['office_id'] == office.office_id:
            office_rank = i + 1
            break

    # Prepare pie chart data
    pie_chart_labels = []
    pie_chart_data = []
    pie_chart_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    
    for i, record in enumerate(all_offices_data[:5]):  # Top 5 offices
        office_name = record['office_name']
        energy = record['total_energy'] or 0
        percentage = (energy / total_all_energy * 100) if total_all_energy > 0 else 0
        
        # Anonymize office names except for the logged-in user's office
        if record['office_id'] == office.office_id:
            display_name = office_name
        else:
            display_name = f"Office {i + 1}"
        
        pie_chart_labels.append(display_name)
        pie_chart_data.append(percentage)

    # Get week data for chart
    if selected_week:
        week_start = date.fromisoformat(selected_week)
        week_end = week_start + timedelta(days=6)
        week_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=week_start,
            date__lte=week_end
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh'),
            peak_power=Max('peak_power_w')
        ).order_by('date')
        
        date_dict = {record['date']: record['total_energy'] or 0 for record in week_data}
        peak_dict = {record['date']: record['peak_power'] or 0 for record in week_data}
        chart_labels = []
        chart_dates = []
        chart_data = []
        chart_peak_power = []
        current = week_start
        while current <= week_end:
            chart_labels.append(current.strftime('%a'))
            chart_dates.append(current.strftime('%A - %B %d, %Y'))
            chart_data.append(date_dict.get(current, 0))
            chart_peak_power.append(peak_dict.get(current, 0))
            current += timedelta(days=1)
    elif selected_date:
        week_start = selected_date - timedelta(days=6)
        week_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=week_start,
            date__lte=selected_date
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh'),
            peak_power=Max('peak_power_w')
        ).order_by('date')
        
        date_dict = {record['date']: record['total_energy'] or 0 for record in week_data}
        peak_dict = {record['date']: record['peak_power'] or 0 for record in week_data}
        chart_labels = []
        chart_dates = []
        chart_data = []
        chart_peak_power = []
        current = week_start
        while current <= selected_date:
            chart_labels.append(current.strftime('%a'))
            chart_dates.append(current.strftime('%A - %B %d, %Y'))
            chart_data.append(date_dict.get(current, 0))
            chart_peak_power.append(peak_dict.get(current, 0))
            current += timedelta(days=1)
    else:
        # For month/year filters, get last 7 days with data
        week_data = SensorReading.objects.filter(
            device__in=devices,
            **filter_kwargs
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh'),
            peak_power=Max('peak_power_w')
        ).order_by('-date')[:7]
        week_data = list(reversed(week_data))
        
        chart_labels = []
        chart_dates = []
        chart_data = []
        chart_peak_power = []
        for record in week_data:
            chart_labels.append(record['date'].strftime('%a'))
            chart_dates.append(record['date'].strftime('%A - %B %d, %Y'))
            chart_data.append(record['total_energy'] or 0)
            chart_peak_power.append(record['peak_power'] or 0)

    # Calculate rank change vs previous period based on level
    if level == 'day':
        # Compare with yesterday
        prev_date = selected_date - timedelta(days=1)
        prev_week_energy = SensorReading.objects.filter(
            device__in=devices,
            date=prev_date
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
        current_week_energy = office_energy
        comparison_label = 'vs Yesterday'
    elif level == 'month':
        # Compare with previous month
        prev_year = int(selected_year)
        prev_month = int(selected_month) - 1
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        
        prev_week_energy = SensorReading.objects.filter(
            device__in=devices,
            date__year=prev_year,
            date__month=prev_month
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
        current_week_energy = office_energy
        comparison_label = 'vs Previous Month'
    else:
        # For year, compare with previous year
        prev_year = int(selected_year) - 1
        prev_week_energy = SensorReading.objects.filter(
            device__in=devices,
            date__year=prev_year
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
        current_week_energy = office_energy
        comparison_label = 'vs Previous Year'
    
    if prev_week_energy > 0:
        rank_change = ((current_week_energy - prev_week_energy) / prev_week_energy) * 100
        rank_change = max(min(rank_change, 999.9), -999.9)
    else:
        rank_change = 100.0 if current_week_energy > 0 else 0

    # Get threshold and determine status with scaled thresholds
    base_thresholds = get_base_thresholds()
    scaled_thresholds = get_scaled_thresholds(base_thresholds, level)
    
    if office_energy > scaled_thresholds['energy_moderate_max']:
        energy_status = 'High'
        status_class = 'status-high'
    elif office_energy > scaled_thresholds['energy_efficient_max']:
        energy_status = 'Moderate'
        status_class = 'status-moderate'
    else:
        energy_status = 'Efficient'
        status_class = 'status-efficient'
    
    is_over_limit = office_energy > scaled_thresholds['energy_moderate_max']

    # Format rank with proper suffix
    rank_suffix = 'th'
    if office_rank == 1:
        rank_suffix = 'st'
    elif office_rank == 2:
        rank_suffix = 'nd'
    elif office_rank == 3:
        rank_suffix = 'rd'
    
    formatted_rank = f"{office_rank}{rank_suffix}"
    
    # Format display date based on level
    if level == 'month' and selected_month and selected_year:
        from datetime import date
        display_date = date(int(selected_year), int(selected_month), 1).strftime('%B %Y')
    elif level == 'year' and selected_year:
        display_date = selected_year
    elif selected_date:
        display_date = selected_date
    else:
        display_date = None
    
    context = {
        'office': office,
        'selected_date': selected_date,
        'display_date': display_date,
        'day_options': day_options,
        'week_options': week_options,
        'month_options': month_options,
        'year_options': year_options,
        'selected_day': selected_day,
        'selected_week': selected_week,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'latest_day_display': latest_day_display,
        'level': level,
        'office_energy_usage': f"{office_energy:.1f}",
        'office_cost_predicted': f"{office_cost:.2f}",
        'office_co2_emission': f"{office_co2:.1f}",
        'office_share_percentage': f"{office_share_percentage:.1f}",
        'office_rank': formatted_rank,
        'total_offices': len(all_offices_data),

        'rank_change': f"{abs(rank_change):.1f}",
        'rank_change_direction': 'increase' if rank_change >= 0 else 'decrease',
        'comparison_label': comparison_label,
        'energy_status': energy_status,
        'status_class': status_class,
        'is_over_limit': is_over_limit,
        'chart_labels': json.dumps(chart_labels),
        'chart_dates': json.dumps(chart_dates),
        'chart_data': json.dumps(chart_data),
        'chart_peak_power': json.dumps(chart_peak_power),
        'pie_chart_labels': json.dumps(pie_chart_labels),
        'pie_chart_data': json.dumps(pie_chart_data),
        'unread_notifications_count': unread_notifications_count,
    }
    return render(request, 'users/userUsage.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def user_reports(request):
    from django.db.models import Sum, Max, Min
    ExtractYear, ExtractMonth, _ = get_db_functions()
    timezone, dt, timedelta, date = get_timezone_utils()
    from ..sensors.models import SensorReading

    office = request.user
    devices = office.devices.all()
    
    # Get unread notifications count
    unread_notifications_count = get_unread_notifications_count(office)

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Auto-select latest data if no filters provided
    if not any([selected_day, selected_month, selected_year, selected_week]):
        latest_data = SensorReading.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
        if latest_data['latest_date']:
            latest_date = latest_data['latest_date']
            selected_month = str(latest_date.month)
            selected_year = str(latest_date.year)

    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
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

    # Week options: filtered by selected month/year if available
    def get_user_week_options(devices, selected_month=None, selected_year=None):
        from django.db.models import Min
        from django.db.models.functions import ExtractYear, ExtractMonth

        # If month and year are selected, filter weeks for that specific month/year
        if selected_month and selected_year:
            months = [{'month': int(selected_month), 'year': int(selected_year)}]
        else:
            # Get distinct months with data
            months = SensorReading.objects.filter(
                device__in=devices
            ).annotate(
                month=ExtractMonth('date'),
                year=ExtractYear('date')
            ).values('month', 'year').distinct().order_by('year', 'month')

        week_options = []
        for m in months:
            year = m['year']
            month = m['month']

            # Get all dates in this month with data
            dates_in_month = SensorReading.objects.filter(
                device__in=devices
            ).filter(
                date__year=year,
                date__month=month
            ).dates('date', 'day')

            if not dates_in_month:
                continue

            min_date = min(dates_in_month)
            max_date = max(dates_in_month)

            # Calculate weeks: start on the first day of the month
            from datetime import date, timedelta
            first_day = date(year, month, 1)
            start_of_month = first_day
            week_num = 1
            current_start = start_of_month
            while current_start <= max_date:
                current_end = min(current_start + timedelta(days=6), max_date)
                # Check if there is data in this week
                # Always include Week 1, and others if there is data
                if week_num == 1 or any(d >= current_start and d <= current_end for d in dates_in_month):
                    week_options.append({
                        'value': current_start.strftime('%Y-%m-%d'),
                        'name': f"Week {week_num}"
                    })
                current_start += timedelta(days=7)
                week_num += 1

        return week_options

    week_options = get_user_week_options(devices, selected_month, selected_year)
    
    # Auto-select latest week if no week selected but month/year are set
    if not selected_week and selected_month and selected_year and week_options:
        selected_week = week_options[-1]['value']  # Latest week

    # Determine filter kwargs and level
    def determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices):
        from datetime import timedelta
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
        elif selected_week:
            try:
                week_start = date.fromisoformat(selected_week)
                week_end = week_start + timedelta(days=6)
                filter_kwargs = {'date__gte': week_start, 'date__lte': week_end}
                level = 'week'
                selected_month = str(week_start.month)
                selected_year = str(week_start.year)
            except ValueError:
                selected_week = None
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
                selected_month = str(latest_date.month)
                selected_year = str(latest_date.year)
                level = 'day'

        return filter_kwargs, selected_date, level, selected_month, selected_year

    filter_kwargs, selected_date, level, selected_month, selected_year = determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices)

    if not filter_kwargs:
        # No data, handle gracefully
        context = {
            'office': office,
            'week_options': week_options,
            'month_options': month_options,
            'year_options': year_options,
            'day_options': day_options,
            'selected_day': selected_day,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'selected_week': selected_week,
            'total_energy_usage': '0.00',
            'highest_usage_day': 'N/A',
            'cost_predicted': '₱0.00',
            'co2_emission': '0.00',
            'office_status': 'ACTIVE',
            'best_performing_day': 'N/A',
            'chart_labels': json.dumps([]),
            'chart_values': json.dumps([]),
            'recommendation': 'No data available.',
        }
        return render(request, 'users/userReports.html', context)

    # Fetch data with historical rates
    period_readings = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    )

    total_energy_usage = period_readings.aggregate(total=Sum('total_energy_kwh'))['total'] or 0
    period_metrics = calculate_energy_metrics_with_historical_rates(period_readings)
    cost_predicted = period_metrics['total_cost']
    co2_emission = period_metrics['total_co2']

    # Prepare chart data based on level
    import calendar
    if level == 'day':
        # Show hourly data if available, otherwise just the day
        chart_labels = [selected_date.strftime('%Y-%m-%d')]
        chart_values = [total_energy_usage]
        chart_peak_power = [SensorReading.objects.filter(
            device__in=devices, **filter_kwargs
        ).aggregate(peak=Max('peak_power_w'))['peak'] or 0]
        highest_usage_day = selected_date.strftime('%Y-%m-%d')
        best_performing_day = selected_date.strftime('%Y-%m-%d')
    elif level == 'week':
        # Show daily data for the week
        week_start = date.fromisoformat(selected_week)
        week_end = week_start + timedelta(days=6)
        
        daily_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=week_start,
            date__lte=week_end
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh'),
            peak_power=Max('peak_power_w')
        ).order_by('date')
        
        daily_energy = {record['date']: record['total_energy'] or 0 for record in daily_data}
        daily_peak = {record['date']: record['peak_power'] or 0 for record in daily_data}
        
        chart_labels = []
        chart_values = []
        chart_peak_power = []
        current = week_start
        while current <= week_end:
            chart_labels.append(current.strftime('%A'))
            chart_values.append(daily_energy.get(current, 0))
            chart_peak_power.append(daily_peak.get(current, 0))
            current += timedelta(days=1)
        
        # Find highest and best performing days
        if chart_values:
            max_energy = max(chart_values)
            max_index = chart_values.index(max_energy)
            highest_usage_day = (week_start + timedelta(days=max_index)).strftime('%Y-%m-%d')
            
            min_energy = min(chart_values)
            min_index = chart_values.index(min_energy)
            best_performing_day = (week_start + timedelta(days=min_index)).strftime('%Y-%m-%d')
        else:
            highest_usage_day = 'N/A'
            best_performing_day = 'N/A'
    elif level == 'month':
        # Show daily data for the month
        start_date = date(int(selected_year), int(selected_month), 1)
        end_date = date(int(selected_year), int(selected_month), calendar.monthrange(int(selected_year), int(selected_month))[1])
        
        daily_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=start_date,
            date__lte=end_date
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh'),
            peak_power=Max('peak_power_w')
        ).order_by('date')
        
        daily_energy = {record['date']: record['total_energy'] or 0 for record in daily_data}
        daily_peak = {record['date']: record['peak_power'] or 0 for record in daily_data}
        
        chart_labels = []
        chart_values = []
        chart_peak_power = []
        current = start_date
        while current <= end_date:
            chart_labels.append(current.strftime('%d'))
            chart_values.append(daily_energy.get(current, 0))
            chart_peak_power.append(daily_peak.get(current, 0))
            current += timedelta(days=1)
        
        # Find highest and best performing days
        if chart_values and any(v > 0 for v in chart_values):
            max_energy = max(chart_values)
            max_index = chart_values.index(max_energy)
            highest_usage_day = (start_date + timedelta(days=max_index)).strftime('%Y-%m-%d')
            
            min_energy = min(v for v in chart_values if v > 0) if any(v > 0 for v in chart_values) else 0
            min_index = next(i for i, v in enumerate(chart_values) if v == min_energy)
            best_performing_day = (start_date + timedelta(days=min_index)).strftime('%Y-%m-%d')
        else:
            highest_usage_day = 'N/A'
            best_performing_day = 'N/A'

    # Office status based on energy usage with scaled thresholds
    base_thresholds = get_base_thresholds()
    scaled_thresholds = get_scaled_thresholds(base_thresholds, level)
    energy_efficient_max = scaled_thresholds['energy_efficient_max']
    energy_moderate_max = scaled_thresholds['energy_moderate_max']
    
    if total_energy_usage > energy_moderate_max:
        office_status = 'HIGH'
        energy_status = 'high'
    elif total_energy_usage > energy_efficient_max:
        office_status = 'MODERATE'
        energy_status = 'moderate'
    else:
        office_status = 'ACTIVE'
        energy_status = 'efficient'
    
    # Cost status (based on energy)
    cost_status = energy_status
    
    # CO2 status
    if co2_emission > scaled_thresholds['co2_moderate_max']:
        co2_status = 'high'
    elif co2_emission > scaled_thresholds['co2_efficient_max']:
        co2_status = 'moderate'
    else:
        co2_status = 'efficient'
    
    # Status card shows overall office status
    status_status = energy_status
    
    # Highest day card - neutral color
    highest_status = 'efficient'

    # Dynamic recommendation based on usage and threshold
    def generate_recommendation(total_energy, energy_efficient_max, energy_moderate_max, level, chart_values):
        # Calculate average and peak from chart data
        avg_usage = sum(chart_values) / len(chart_values) if chart_values else 0
        peak_usage = max(chart_values) if chart_values else 0
        
        # Determine status
        if total_energy > energy_moderate_max:
            # High usage - provide specific recommendations
            excess = total_energy - energy_moderate_max
            recommendations = [
                f"Energy usage ({total_energy:.2f} kWh) exceeds the moderate threshold ({energy_moderate_max:.2f} kWh) by {excess:.2f} kWh. ",
            ]
            
            # Add specific tips based on peak usage
            if peak_usage > energy_moderate_max:
                recommendations.append("Consider reducing consumption during peak hours by turning off unused equipment and optimizing HVAC settings.")
            else:
                recommendations.append("Spread out energy-intensive activities throughout the day to avoid concentration of usage.")
                
        elif total_energy > energy_efficient_max:
            # Moderate usage - provide improvement suggestions
            recommendations = [
                f"Energy usage is moderate ({total_energy:.2f} kWh). ",
                f"You're {((energy_moderate_max - total_energy) / energy_moderate_max * 100):.1f}% away from high usage. ",
                "Consider implementing energy-saving practices like using natural lighting and scheduling equipment usage during off-peak hours."
            ]
        else:
            # Efficient usage - provide encouragement
            recommendations = [
                f"Excellent! Energy usage is within efficient limits ({total_energy:.2f} kWh). ",
                "Keep up the good work by maintaining current energy-saving practices."
            ]
        
        return "".join(recommendations)
    
    recommendation = generate_recommendation(total_energy_usage, energy_efficient_max, energy_moderate_max, level, chart_values)

    # Get calendar data for current month
    from django.utils import timezone
    now = timezone.now().date()
    calendar_year = int(selected_year) if selected_year else now.year
    calendar_month = int(selected_month) if selected_month else now.month
    
    calendar_data = SensorReading.objects.filter(
        device__in=devices,
        date__year=calendar_year,
        date__month=calendar_month
    ).values('date').annotate(
        total_energy=Sum('total_energy_kwh')
    )
    
    # Create calendar energy map
    calendar_energy = {}
    for record in calendar_data:
        day = record['date'].day
        energy = record['total_energy'] or 0
        calendar_energy[day] = energy

    context = {
        'office': office,
        'week_options': week_options,
        'month_options': month_options,
        'year_options': year_options,
        'day_options': day_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_week': selected_week,
        'level': level,
        'total_energy_usage': f"{total_energy_usage:.2f}",
        'highest_usage_day': highest_usage_day,
        'cost_predicted': f"₱{cost_predicted:.2f}",
        'co2_emission': f"{co2_emission:.2f}",
        'office_status': office_status,
        'best_performing_day': best_performing_day,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
        'chart_peak_power': json.dumps(chart_peak_power),
        'chart_colors': json.dumps(["#dc3545" if v > energy_moderate_max else "#ffc107" if v > energy_efficient_max else "#28a745" for v in chart_values]),
        'recommendation': recommendation,
        'calendar_energy': json.dumps(calendar_energy),
        'calendar_year': calendar_year,
        'calendar_month': calendar_month,
        'energy_efficient_max': energy_efficient_max,
        'energy_moderate_max': energy_moderate_max,
        'energy_status': energy_status,
        'cost_status': cost_status,
        'co2_status': co2_status,
        'status_status': status_status,
        'highest_status': highest_status,
        'unread_notifications_count': unread_notifications_count,
    }
    return render(request, 'users/userReports.html', context)



@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def user_energy_cost(request):
    from django.db.models import Sum, Max
    from django.db.models.functions import ExtractYear, ExtractMonth
    from django.utils import timezone
    from datetime import date, timedelta
    from ..sensors.models import SensorReading
    from datetime import datetime as dt
    from calendar import monthrange
    import json

    office = request.user
    devices = office.devices.all()
    
    # Get unread notifications count
    unread_notifications_count = get_unread_notifications_count(office)
    
    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')
    
    # Auto-select latest data if no filters provided
    if not any([selected_day, selected_month, selected_year, selected_week]):
        latest_data = SensorReading.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
        if latest_data['latest_date']:
            latest_date = latest_data['latest_date']
            selected_month = str(latest_date.month)
            selected_year = str(latest_date.year)
    
    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
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
    
    # Week options function
    def get_user_week_options(devices, selected_month=None, selected_year=None):
        from django.db.models.functions import ExtractYear, ExtractMonth
        
        if selected_month and selected_year:
            months = [{'month': int(selected_month), 'year': int(selected_year)}]
        else:
            months = SensorReading.objects.filter(
                device__in=devices
            ).annotate(
                month=ExtractMonth('date'),
                year=ExtractYear('date')
            ).values('month', 'year').distinct().order_by('year', 'month')
        
        week_options = []
        for m in months:
            year = m['year']
            month = m['month']
            
            dates_in_month = SensorReading.objects.filter(
                device__in=devices
            ).filter(
                date__year=year,
                date__month=month
            ).dates('date', 'day')
            
            if not dates_in_month:
                continue
            
            min_date = min(dates_in_month)
            max_date = max(dates_in_month)
            
            first_day = date(year, month, 1)
            start_of_month = first_day
            week_num = 1
            current_start = start_of_month
            while current_start <= max_date:
                current_end = min(current_start + timedelta(days=6), max_date)
                if week_num == 1 or any(d >= current_start and d <= current_end for d in dates_in_month):
                    week_options.append({
                        'value': current_start.strftime('%Y-%m-%d'),
                        'name': f"Week {week_num}"
                    })
                current_start += timedelta(days=7)
                week_num += 1
        
        return week_options
    
    week_options = get_user_week_options(devices, selected_month, selected_year)
    
    # Auto-select latest week if no week selected but month/year are set
    if not selected_week and selected_month and selected_year and week_options:
        selected_week = week_options[-1]['value']  # Latest week
    
    # Determine filter kwargs and level
    def determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices):
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
        elif selected_week:
            try:
                week_start = date.fromisoformat(selected_week)
                week_end = week_start + timedelta(days=6)
                filter_kwargs = {'date__gte': week_start, 'date__lte': week_end}
                level = 'week'
                selected_month = str(week_start.month)
                selected_year = str(week_start.year)
            except ValueError:
                selected_week = None
        elif selected_month and selected_year:
            filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
            level = 'month'
        elif selected_year:
            filter_kwargs = {'date__year': int(selected_year)}
            level = 'year'
        else:
            latest_data = SensorReading.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
            latest_date = latest_data['latest_date']
            if latest_date:
                filter_kwargs = {'date': latest_date}
                selected_date = latest_date
                selected_month = str(latest_date.month)
                selected_year = str(latest_date.year)
                level = 'day'
        
        return filter_kwargs, selected_date, level, selected_month, selected_year
    
    filter_kwargs, selected_date, level, selected_month, selected_year = determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices)
    
    if not filter_kwargs:
        context = {
            'office': office,
            'week_options': week_options,
            'month_options': month_options,
            'year_options': year_options,
            'day_options': day_options,
            'selected_day': selected_day,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'selected_week': selected_week,
            'total_energy': '0.00',
            'total_cost': '₱0.00',
            'avg_daily_cost': '₱0.00',
            'highest_cost_day': 'N/A',
            'last_month_cost': '₱0.00',
            'current_month_so_far_cost': '₱0.00',
            'predicted_total_cost': '₱0.00',
            'estimate_saving': '₱0.00',
            'chart_labels': json.dumps([]),
            'chart_data': json.dumps([]),
        }
        return render(request, 'users/userEnergyCost.html', context)
    
    # Get readings and calculate with historical rates
    filtered_readings = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    )
    
    num_days = filtered_readings.dates('date', 'day').distinct().count() or 1
    total_energy = filtered_readings.aggregate(total=Sum('total_energy_kwh'))['total'] or 0
    
    metrics = calculate_energy_metrics_with_historical_rates(filtered_readings)
    total_cost = metrics['total_cost']
    avg_daily_cost = total_cost / num_days if num_days > 0 else 0
    
    # Calculate period start and end based on level
    now = timezone.now().date()
    if level == 'week':
        if selected_week:
            period_start = date.fromisoformat(selected_week)
        else:
            period_start = now - timedelta(days=now.weekday())
        period_end = period_start + timedelta(days=6)
    elif level == 'month':
        year = int(selected_year) if selected_year else dt.now().year
        month = int(selected_month) if selected_month else dt.now().month
        period_start = date(year, month, 1)
        _, last_day = monthrange(year, month)
        period_end = date(year, month, last_day)
    elif level == 'year':
        period_start = date(int(selected_year), 1, 1)
        period_end = date(int(selected_year), 12, 31)
    else:  # day
        period_start = selected_date
        period_end = selected_date
    
    # Calculate previous period
    if level == 'week':
        prev_start = period_start - timedelta(days=7)
        prev_end = period_end - timedelta(days=7)
    elif level == 'month':
        year = int(selected_year) if selected_year else dt.now().year
        month = int(selected_month) if selected_month else dt.now().month
        prev_year = year
        prev_month = month - 1
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        prev_start = date(prev_year, prev_month, 1)
        _, last_day = monthrange(prev_year, prev_month)
        prev_end = date(prev_year, prev_month, last_day)
    elif level == 'year':
        prev_start = date(int(selected_year) - 1, 1, 1)
        prev_end = date(int(selected_year) - 1, 12, 31)
    else:  # day
        prev_start = period_start - timedelta(days=1)
        prev_end = period_end - timedelta(days=1)
    
    # Previous cost with historical rates
    prev_readings = SensorReading.objects.filter(
        device__in=devices,
        date__gte=prev_start,
        date__lte=prev_end
    )
    prev_metrics = calculate_energy_metrics_with_historical_rates(prev_readings)
    prev_cost = prev_metrics['total_cost']
    
    # So far cost with historical rates
    so_far_end = min(period_end, now)
    so_far_readings = SensorReading.objects.filter(
        device__in=devices,
        date__gte=period_start,
        date__lte=so_far_end
    )
    so_far_metrics = calculate_energy_metrics_with_historical_rates(so_far_readings)
    so_far_cost = so_far_metrics['total_cost']
    
    # Predicted cost
    total_days = (period_end - period_start).days + 1
    days_so_far = (so_far_end - period_start).days + 1 if so_far_end >= period_start else 0
    if days_so_far > 0 and period_end > now:
        avg_daily = so_far_cost / days_so_far
        predicted_cost = avg_daily * total_days
    else:
        predicted_cost = so_far_cost
    
    # Savings
    savings = prev_cost - predicted_cost if prev_cost > predicted_cost else 0
    
    # Highest cost day/period
    if level == 'day':
        highest_cost_day = selected_date.strftime('%Y-%m-%d')
    else:
        daily_costs = SensorReading.objects.filter(
            device__in=devices,
            **filter_kwargs
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('-total_energy')
        
        if daily_costs:
            highest_cost_day = daily_costs.first()['date'].strftime('%Y-%m-%d')
        else:
            highest_cost_day = 'N/A'
    
    # Chart data based on selected filter
    if level == 'week':
        week_date = date.fromisoformat(selected_week)
        start_date = week_date
        end_date = start_date + timedelta(days=6)
        chart_dates = [start_date + timedelta(days=i) for i in range(7)]
        chart_labels = [[d.strftime('%A'), d.strftime('%Y-%m-%d')] for d in chart_dates]
        chart_data = []
        for d in chart_dates:
            energy = SensorReading.objects.filter(
                device__in=devices,
                date=d
            ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
            chart_data.append(energy)
    elif level == 'month':
        year = int(selected_year) if selected_year else dt.now().year
        month = int(selected_month) if selected_month else dt.now().month
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        chart_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        chart_labels = [[d.strftime('%d'), d.strftime('%Y-%m-%d')] for d in chart_dates]
        chart_data = []
        for d in chart_dates:
            energy = SensorReading.objects.filter(
                device__in=devices,
                date=d
            ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
            chart_data.append(energy)
    elif level == 'year':
        monthly_data = SensorReading.objects.filter(
            device__in=devices,
            date__year=int(selected_year)
        ).annotate(
            month=ExtractMonth('date')
        ).values('month').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('month')
        chart_labels = [['Jan', 'January'], ['Feb', 'February'], ['Mar', 'March'], ['Apr', 'April'], 
                       ['May', 'May'], ['Jun', 'June'], ['Jul', 'July'], ['Aug', 'August'], 
                       ['Sep', 'September'], ['Oct', 'October'], ['Nov', 'November'], ['Dec', 'December']]
        chart_data = [0] * 12
        for item in monthly_data:
            energy = item['total_energy'] or 0
            chart_data[item['month'] - 1] = energy
    else:  # day
        chart_labels = [[selected_date.strftime('%A'), selected_date.strftime('%Y-%m-%d')]]
        chart_data = [total_energy]
    
    # Labels for chart header
    if level == 'week':
        previous_label = f"Previous Week ({prev_start.strftime('%B %d')} - {prev_end.strftime('%d, %Y')})"
        period_label = f"Week ({period_start.strftime('%B %d')} - {period_end.strftime('%d, %Y')})"
    elif level == 'month':
        previous_label = f"{prev_start.strftime('%B %Y')} Total"
        period_label = f"{period_start.strftime('%B %Y')}"
    elif level == 'year':
        previous_label = f"{prev_start.year} Total"
        period_label = f"{selected_year}"
    else:  # day
        previous_label = f"{prev_start.strftime('%B %d, %Y')} Total"
        period_label = f"{period_start.strftime('%B %d, %Y')}"
    
    so_far_label = f"So Far This {level.capitalize()} ({period_label})"
    predicted_label = f"Predicted This {level.capitalize()}"
    savings_label = "Estimated Savings"
    
    # Determine individual card efficiency status
    base_thresholds = get_base_thresholds()
    scaled_thresholds = get_scaled_thresholds(base_thresholds, level)
    
    # Energy card status
    if total_energy > scaled_thresholds['energy_moderate_max']:
        energy_status = 'high'
    elif total_energy > scaled_thresholds['energy_efficient_max']:
        energy_status = 'moderate'
    else:
        energy_status = 'efficient'
    
    # Cost cards status (based on energy)
    cost_status = energy_status
    
    # Average daily cost status
    avg_status = energy_status
    
    # Highest cost day - neutral
    highest_status = 'efficient'
    
    context = {
        'office': office,
        'week_options': week_options,
        'month_options': month_options,
        'year_options': year_options,
        'day_options': day_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_week': selected_week,
        'level': level,
        'total_energy': f"{total_energy:.2f}",
        'total_cost': f"₱{total_cost:.2f}",
        'avg_daily_cost': f"₱{avg_daily_cost:.2f}",
        'highest_cost_day': highest_cost_day,
        'previous_label': previous_label,
        'prev_cost': f"₱{prev_cost:.2f}",
        'so_far_label': so_far_label,
        'so_far_cost': f"₱{so_far_cost:.2f}",
        'predicted_label': predicted_label,
        'predicted_cost': f"₱{predicted_cost:.2f}",
        'savings_label': savings_label,
        'savings': f"₱{savings:.2f}",
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'energy_status': energy_status,
        'cost_status': cost_status,
        'avg_status': avg_status,
        'highest_status': highest_status,
        'unread_notifications_count': unread_notifications_count,
    }
    return render(request, 'users/userEnergyCost.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def user_emmision(request):
    from django.db.models import Sum, Min, Max
    from django.db.models.functions import TruncDate, ExtractYear, ExtractMonth
    from datetime import datetime, timedelta, date
    from calendar import monthrange
    from django.utils import timezone
    import json
    from greenwatts.users.models import Office
    from ..sensors.models import SensorReading
    from datetime import datetime as dt

    office = request.user
    devices = office.devices.all()
    
    # Get unread notifications count
    unread_notifications_count = get_unread_notifications_count(office)

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Auto-select latest data if no filters provided
    if not any([selected_day, selected_month, selected_year, selected_week]):
        latest_data = SensorReading.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
        if latest_data['latest_date']:
            latest_date = latest_data['latest_date']
            selected_month = str(latest_date.month)
            selected_year = str(latest_date.year)

    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
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

    # Week options function
    def get_user_week_options(devices, selected_month=None, selected_year=None):
        from django.db.models.functions import ExtractYear, ExtractMonth
        
        if selected_month and selected_year:
            months = [{'month': int(selected_month), 'year': int(selected_year)}]
        else:
            months = SensorReading.objects.filter(
                device__in=devices
            ).annotate(
                month=ExtractMonth('date'),
                year=ExtractYear('date')
            ).values('month', 'year').distinct().order_by('year', 'month')
        
        week_options = []
        for m in months:
            year = m['year']
            month = m['month']
            
            dates_in_month = SensorReading.objects.filter(
                device__in=devices
            ).filter(
                date__year=year,
                date__month=month
            ).dates('date', 'day')
            
            if not dates_in_month:
                continue
            
            min_date = min(dates_in_month)
            max_date = max(dates_in_month)
            
            first_day = date(year, month, 1)
            start_of_month = first_day
            week_num = 1
            current_start = start_of_month
            while current_start <= max_date:
                current_end = min(current_start + timedelta(days=6), max_date)
                if week_num == 1 or any(d >= current_start and d <= current_end for d in dates_in_month):
                    week_options.append({
                        'value': current_start.strftime('%Y-%m-%d'),
                        'name': f"Week {week_num}"
                    })
                current_start += timedelta(days=7)
                week_num += 1
        
        return week_options

    week_options = get_user_week_options(devices, selected_month, selected_year)
    
    # Auto-select latest week if no week selected but month/year are set
    if not selected_week and selected_month and selected_year and week_options:
        selected_week = week_options[-1]['value']  # Latest week

    # Determine filter kwargs and level
    def determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices):
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
        elif selected_week:
            try:
                week_start = date.fromisoformat(selected_week)
                week_end = week_start + timedelta(days=6)
                filter_kwargs = {'date__gte': week_start, 'date__lte': week_end}
                level = 'week'
                selected_month = str(week_start.month)
                selected_year = str(week_start.year)
            except ValueError:
                selected_week = None
        elif selected_month and selected_year:
            filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
            level = 'month'
        elif selected_year:
            filter_kwargs = {'date__year': int(selected_year)}
            level = 'year'
        else:
            latest_data = SensorReading.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
            latest_date = latest_data['latest_date']
            if latest_date:
                filter_kwargs = {'date': latest_date}
                selected_date = latest_date
                selected_month = str(latest_date.month)
                selected_year = str(latest_date.year)
                level = 'day'
        
        return filter_kwargs, selected_date, level, selected_month, selected_year

    filter_kwargs, selected_date, level, selected_month, selected_year = determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices)

    if not filter_kwargs:
        context = {
            'office': office,
            'week_options': week_options,
            'month_options': month_options,
            'year_options': year_options,
            'selected_week': selected_week,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'previous_week_name': 'N/A',
            'last_week_co2': '0.0',
            'current_week_so_far_co2': '0.0',
            'predicted_week_co2': '0.0',
            'change_percent': '0.00%',
            'change_direction': '▼',
            'change_class': 'green-arrow',
            'chart_labels': json.dumps([]),
            'week_data': json.dumps([]),
            'threshold': 180,
            'co2_efficient_max': 8.0,
        }
        return render(request, 'users/userEmmision.html', context)

    # Get CO2 data with historical rates
    filtered_readings = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    )
    
    energy_data = filtered_readings.aggregate(total=Sum('total_energy_kwh'))['total'] or 0
    metrics = calculate_energy_metrics_with_historical_rates(filtered_readings)
    co2_data = metrics['total_co2']

    # Calculate previous period for comparison
    if level == 'week':
        week_start = date.fromisoformat(selected_week)
        week_end = week_start + timedelta(days=6)
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_end - timedelta(days=7)
        previous_label = f"Previous Week"
    elif level == 'month':
        current_year = int(selected_year)
        current_month = int(selected_month)
        prev_year = current_year
        prev_month = current_month - 1
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        prev_week_start = date(prev_year, prev_month, 1)
        _, last_day = monthrange(prev_year, prev_month)
        prev_week_end = date(prev_year, prev_month, last_day)
        week_start = date(current_year, current_month, 1)
        _, last_day = monthrange(current_year, current_month)
        week_end = date(current_year, current_month, last_day)
        previous_label = f"Previous Month"
    else:
        # Default to week-based calculation
        now = timezone.now().date()
        week_start = now - timedelta(days=6)
        week_end = now
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_end - timedelta(days=7)
        previous_label = f"Previous Week"

    # Previous period CO2 with historical rates
    prev_readings = SensorReading.objects.filter(
        device__in=devices,
        date__gte=prev_week_start,
        date__lte=prev_week_end
    )
    prev_metrics = calculate_energy_metrics_with_historical_rates(prev_readings)
    last_week_co2 = prev_metrics['total_co2']

    # Current period so far CO2 with historical rates
    now = timezone.now().date()
    current_end = min(week_end, now)
    current_readings = SensorReading.objects.filter(
        device__in=devices,
        date__gte=week_start,
        date__lte=current_end
    )
    current_metrics = calculate_energy_metrics_with_historical_rates(current_readings)
    current_week_so_far_co2 = current_metrics['total_co2']

    # Predicted CO2
    if level == 'week':
        days_so_far = (current_end - week_start).days + 1 if current_end >= week_start else 1
        avg_daily_co2 = current_week_so_far_co2 / days_so_far if days_so_far > 0 else 0
        predicted_week_co2 = avg_daily_co2 * 7
    elif level == 'month':
        days_so_far = (current_end - week_start).days + 1 if current_end >= week_start else 1
        _, days_in_month = monthrange(int(selected_year), int(selected_month))
        avg_daily_co2 = current_week_so_far_co2 / days_so_far if days_so_far > 0 else 0
        predicted_week_co2 = avg_daily_co2 * days_in_month
    else:
        predicted_week_co2 = current_week_so_far_co2 * 2

    # Change in emissions
    if last_week_co2 > 0:
        change_percent = ((current_week_so_far_co2 - last_week_co2) / last_week_co2) * 100
    else:
        change_percent = 0
    change_direction = '▲' if change_percent > 0 else '▼'
    change_class = 'red-arrow' if change_percent > 0 else 'green-arrow'

    # Chart data based on level
    if level == 'week':
        daily_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=week_start,
            date__lte=week_end
        ).annotate(
            day_date=TruncDate('date')
        ).values('day_date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('day_date')
        
        date_range = []
        current = week_start
        while current <= week_end:
            date_range.append(current)
            current += timedelta(days=1)
        
        co2_settings = CO2Settings.get_current_rate()
        date_dict = {item['day_date']: (item['total_energy'] or 0) * co2_settings.co2_emission_factor for item in daily_data}
        week_data = []
        labels = []
        for d in date_range:
            label = d.strftime('%a %d')
            labels.append(label)
            week_data.append(date_dict.get(d, 0))
    elif level == 'month':
        daily_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=week_start,
            date__lte=week_end
        ).annotate(
            day_date=TruncDate('date')
        ).values('day_date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('day_date')
        
        date_range = []
        current = week_start
        while current <= week_end:
            date_range.append(current)
            current += timedelta(days=1)
        
        co2_settings = CO2Settings.get_current_rate()
        date_dict = {item['day_date']: (item['total_energy'] or 0) * co2_settings.co2_emission_factor for item in daily_data}
        week_data = []
        labels = []
        for d in date_range:
            label = d.strftime('%d')
            labels.append(label)
            week_data.append(date_dict.get(d, 0))
    else:
        # Default to last 7 days
        end_date = now
        start_date = end_date - timedelta(days=6)
        daily_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=start_date,
            date__lte=end_date
        ).annotate(
            day_date=TruncDate('date')
        ).values('day_date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('day_date')
        
        date_range = []
        current = start_date
        while current <= end_date:
            date_range.append(current)
            current += timedelta(days=1)
        
        co2_settings = CO2Settings.get_current_rate()
        date_dict = {item['day_date']: (item['total_energy'] or 0) * co2_settings.co2_emission_factor for item in daily_data}
        week_data = []
        labels = []
        for d in date_range:
            label = d.strftime('%a %d')
            labels.append(label)
            week_data.append(date_dict.get(d, 0))

    # Get base (daily) CO2 threshold for chart since we show daily data points
    base_thresholds = get_base_thresholds()
    threshold_value = base_thresholds['co2_moderate_max']
    
    # Determine individual card efficiency status based on CO2 emissions
    scaled_thresholds = get_scaled_thresholds(base_thresholds, level)
    
    # Current week CO2 status
    if current_week_so_far_co2 > scaled_thresholds['co2_moderate_max']:
        current_status = 'high'
    elif current_week_so_far_co2 > scaled_thresholds['co2_efficient_max']:
        current_status = 'moderate'
    else:
        current_status = 'efficient'
    
    # Predicted week CO2 status
    if predicted_week_co2 > scaled_thresholds['co2_moderate_max']:
        predicted_status = 'high'
    elif predicted_week_co2 > scaled_thresholds['co2_efficient_max']:
        predicted_status = 'moderate'
    else:
        predicted_status = 'efficient'
    
    # Change card - neutral
    change_status = 'efficient'
    
    # Threshold card - neutral
    threshold_status = 'efficient'

    context = {
        'office': office,
        'week_options': week_options,
        'month_options': month_options,
        'year_options': year_options,
        'selected_week': selected_week,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'previous_week_name': previous_label,
        'last_week_co2': f"{last_week_co2:.1f}",
        'current_week_so_far_co2': f"{current_week_so_far_co2:.1f}",
        'predicted_week_co2': f"{predicted_week_co2:.0f}",
        'change_percent': f"{abs(change_percent):.2f}%",
        'change_direction': change_direction,
        'change_class': change_class,
        'chart_labels': json.dumps(labels),
        'week_data': json.dumps(week_data),
        'threshold': threshold_value,
        'co2_efficient_max': base_thresholds['co2_efficient_max'],
        'current_status': current_status,
        'predicted_status': predicted_status,
        'change_status': change_status,
        'threshold_status': threshold_status,
        'unread_notifications_count': unread_notifications_count,
    }
    return render(request, 'users/userEmmision.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def export_user_reports(request):
    from django.db.models import Sum, Max
    from django.db.models.functions import ExtractYear, ExtractMonth
    from datetime import timedelta, date
    from datetime import datetime as dt
    from ..sensors.models import SensorReading
    import calendar
    
    office = request.user
    devices = office.devices.all()
    
    # Get filter parameters
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')
    
    # Use same filter logic as main view
    def determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices):
        from datetime import timedelta
        filter_kwargs = {}
        selected_date = None
        level = 'day'

        if selected_day:
            try:
                month_str, day_str, year_str = selected_day.split('/')
                selected_date = date(int(year_str), int(month_str), int(day_str))
                filter_kwargs = {'date': selected_date}
                level = 'day'
            except ValueError:
                selected_date = None
        elif selected_week:
            try:
                week_start = date.fromisoformat(selected_week)
                week_end = week_start + timedelta(days=6)
                filter_kwargs = {'date__gte': week_start, 'date__lte': week_end}
                level = 'week'
            except ValueError:
                selected_week = None
        elif selected_month and selected_year:
            filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
            level = 'month'
        elif selected_year:
            filter_kwargs = {'date__year': int(selected_year)}
            level = 'year'
        else:
            # Default to latest date
            latest_data = SensorReading.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
            latest_date = latest_data['latest_date']
            if latest_date:
                filter_kwargs = {'date': latest_date}
                level = 'day'

        return filter_kwargs, level
    
    filter_kwargs, level = determine_user_filter_level(selected_day, selected_month, selected_year, selected_week, devices)
    
    if not filter_kwargs:
        # No data case
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="user_report_no_data.csv"'
        writer = csv.writer(response)
        writer.writerow(['No data available'])
        return response
    
    # Get data based on filter
    export_data = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    ).values('date').annotate(
        total_energy=Sum('total_energy_kwh')
    ).order_by('date')
    
    response = HttpResponse(content_type='text/csv')
    
    # Generate filename based on filter
    if level == 'day':
        filename = f"user_report_day_{selected_day.replace('/', '_')}_{office.username}.csv"
    elif level == 'week':
        filename = f"user_report_week_{selected_week}_{office.username}.csv"
    elif level == 'month':
        filename = f"user_report_month_{selected_month}_{selected_year}_{office.username}.csv"
    elif level == 'year':
        filename = f"user_report_year_{selected_year}_{office.username}.csv"
    else:
        filename = f"user_report_{office.username}.csv"
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Energy Usage (kWh)', 'Cost Estimate (PHP)', 'CO2 Emission (kg)'])
    
    for record in export_data:
        energy = record['total_energy'] or 0
        # Calculate cost and CO2 using historical rates for this specific date
        daily_readings = SensorReading.objects.filter(
            device__in=devices,
            date=record['date']
        )
        daily_metrics = calculate_energy_metrics_with_historical_rates(daily_readings)
        
        writer.writerow([
            record['date'].strftime('%Y-%m-%d'),
            f"{energy:.2f}",
            f"{daily_metrics['total_cost']:.2f}",
            f"{daily_metrics['total_co2']:.2f}"
        ])
    
    return response

@login_required
def get_user_days(request):
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    if not month or not year:
        return JsonResponse({'status': 'error', 'message': 'Month and year required'})
    
    try:
        office = request.user
        devices = office.devices.all()
        
        days = SensorReading.objects.filter(
            date__year=int(year),
            date__month=int(month),
            device__in=devices
        ).dates('date', 'day').order_by('-date')
        
        day_options = [d.strftime('%m/%d/%Y') for d in days]
        
        return JsonResponse({
            'status': 'success',
            'days': day_options
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@login_required
@login_required
def mark_notifications_read(request):
    if request.method == 'POST':
        office = request.user
        Notification.objects.filter(
            models.Q(target_office=office) | models.Q(is_global=True),
            is_read=False
        ).update(is_read=True)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'})

@login_required
def get_user_weeks(request):
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    try:
        office = request.user
        devices = office.devices.all()
        
        def get_user_week_options(devices, selected_month=None, selected_year=None):
            from django.db.models.functions import ExtractYear, ExtractMonth
            from datetime import date, timedelta

            if selected_month and selected_year:
                months = [{'month': int(selected_month), 'year': int(selected_year)}]
            else:
                months = SensorReading.objects.filter(
                    device__in=devices
                ).annotate(
                    month=ExtractMonth('date'),
                    year=ExtractYear('date')
                ).values('month', 'year').distinct().order_by('year', 'month')

            week_options = []
            for m in months:
                year = m['year']
                month = m['month']

                dates_in_month = SensorReading.objects.filter(
                    device__in=devices
                ).filter(
                    date__year=year,
                    date__month=month
                ).dates('date', 'day')

                if not dates_in_month:
                    continue

                min_date = min(dates_in_month)
                max_date = max(dates_in_month)

                first_day = date(year, month, 1)
                start_of_month = first_day
                week_num = 1
                current_start = start_of_month
                while current_start <= max_date:
                    current_end = min(current_start + timedelta(days=6), max_date)
                    if week_num == 1 or any(d >= current_start and d <= current_end for d in dates_in_month):
                        week_options.append({
                            'value': current_start.strftime('%Y-%m-%d'),
                            'name': f"Week {week_num}"
                        })
                    current_start += timedelta(days=7)
                    week_num += 1

            return week_options
        
        week_options = get_user_week_options(devices, month, year)
        
        return JsonResponse({
            'status': 'success',
            'weeks': week_options
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def resend_otp(request):
    from .lazy_two_factor import lazy_send_otp as send_otp
    from django.core.cache import cache
    from django.utils import timezone
    
    if 'pending_2fa_user' not in request.session:
        return redirect('users:index')
    
    username = request.session.get('pending_2fa_user')
    cooldown_key = f"resend_cooldown_{username}"
    
    # Check cooldown
    last_sent = cache.get(cooldown_key)
    if last_sent:
        remaining = 300 - (timezone.now().timestamp() - last_sent)  # 5 minutes = 300 seconds
        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            messages.error(request, f'Please wait {minutes}m {seconds}s before requesting another code.')
            return redirect('users:verify_otp')
    
    try:
        from .models import Office
        office = Office.objects.get(username=username)
        
        if send_otp(username, office.email):
            # Set cooldown
            cache.set(cooldown_key, timezone.now().timestamp(), timeout=300)
            messages.success(request, 'Verification code sent successfully.')
        else:
            messages.error(request, 'Failed to send verification code. Please try again.')
    except Office.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('users:index')
    
    return redirect('users:verify_otp')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def verify_otp(request):
    from .lazy_two_factor import lazy_verify_otp as check_otp, lazy_trust_device as trust_device
    
    if 'pending_2fa_user' not in request.session:
        return redirect('users:index')
    
    username = request.session.get('pending_2fa_user')
    
    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip()
        
        if check_otp(username, otp):
            # OTP valid - trust device and login
            from .models import Office
            try:
                office = Office.objects.get(username=username)
                device_fingerprint = request.session.get('device_fingerprint')
                trust_device(username, device_fingerprint)
                
                # Clean up session
                del request.session['pending_2fa_user']
                del request.session['device_fingerprint']
                
                # Login user
                auth.login(request, office, backend='django.contrib.auth.backends.ModelBackend')
                return redirect('users:dashboard')
            except Office.DoesNotExist:
                messages.error(request, 'User not found.')
                return redirect('users:index')
        else:
            messages.error(request, 'Invalid or expired verification code.')
    
    return render(request, 'users/verify_otp.html', {'username': username})

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def logout(request):
    auth.logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('users:index')
