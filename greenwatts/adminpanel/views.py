from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.views.decorators.cache import cache_control
from functools import wraps
from .models import Admin, EnergyThreshold, CO2Threshold
from greenwatts.users.models import Office
from ..sensors.models import Device
from ..sensors.models import EnergyRecord
from django.db.models import Sum, F, Max, Q
from django.utils import timezone
from django.db.models.functions import ExtractYear, ExtractMonth
from datetime import datetime, timedelta, date
from .utils import get_random_energy_tip, get_scaled_thresholds
import json
import csv

# Constants
MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
               'July', 'August', 'September', 'October', 'November', 'December']

def get_threshold_for_date(target_date):
    """Get the threshold that was active on a specific date"""
    # Get active thresholds (ended_at is null)
    energy_threshold = EnergyThreshold.objects.filter(ended_at__isnull=True).first()
    co2_threshold = CO2Threshold.objects.filter(ended_at__isnull=True).first()
    
    # If no active threshold, get the latest one
    if not energy_threshold:
        energy_threshold = EnergyThreshold.objects.order_by('-created_at').first()
    if not co2_threshold:
        co2_threshold = CO2Threshold.objects.order_by('-created_at').first()
    
    return {
        'energy_efficient_max': energy_threshold.efficient_max if energy_threshold else 50.0,
        'energy_moderate_max': energy_threshold.moderate_max if energy_threshold else 100.0,
        'co2_efficient_max': co2_threshold.efficient_max if co2_threshold else 8.0,
        'co2_moderate_max': co2_threshold.moderate_max if co2_threshold else 13.0,
    }

def get_valid_office_ids():
    """Get all valid office ids from Office table"""
    return set(Office.objects.values_list('office_id', flat=True))

def get_year_options(valid_office_ids):
    """Get year options: all years with data"""
    years_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    return [str(y) for y in years_with_data]

def get_month_options(valid_office_ids):
    """Get month options: all months with data"""
    months_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')
    return [{'value': str(m), 'name': MONTH_NAMES[m-1]} for m in months_with_data]

def get_day_options(valid_office_ids, selected_month=None, selected_year=None):
    """Get day options: all days with data, or filtered by month/year if selected"""
    if selected_month and selected_year:
        days = EnergyRecord.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')
    else:
        days = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')
    return [d.strftime('%m/%d/%Y') for d in days]

def determine_filter_level(selected_day, selected_month, selected_year, selected_week):
    """Determine filter kwargs and level based on selections"""
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
        latest_data = get_latest_date_filter()
        filter_kwargs = latest_data['filter_kwargs']
        if filter_kwargs:
            selected_date = latest_data['selected_date']
            selected_month = latest_data['selected_month']
            selected_year = latest_data['selected_year']
            level = 'day'

    return filter_kwargs, selected_date, level, selected_month, selected_year

def get_latest_date_filter():
    """Get the latest date from EnergyRecord as default filter"""
    latest_date_qs = EnergyRecord.objects.aggregate(latest_date=Max('date'))
    latest_date = latest_date_qs['latest_date']
    if latest_date:
        return {
            'filter_kwargs': {'date': latest_date},
            'selected_date': latest_date,
            'selected_day': latest_date.strftime('%m/%d/%Y'),
            'selected_month': str(latest_date.month),
            'selected_year': str(latest_date.year)
        }
    return {'filter_kwargs': {}}

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('admin_id'):
            response = redirect('adminpanel:admin_login')
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def get_week_options(valid_office_ids, selected_month=None, selected_year=None):
    from django.db.models import Min
    from django.db.models.functions import ExtractYear, ExtractMonth

    # If month and year are selected, filter weeks for that specific month/year
    if selected_month and selected_year:
        months = [{'month': int(selected_month), 'year': int(selected_year)}]
    else:
        # Get distinct months with data
        months = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).annotate(
            month=ExtractMonth('date'),
            year=ExtractYear('date')
        ).values('month', 'year').distinct().order_by('year', 'month')

    week_options = []
    for m in months:
        year = m['year']
        month = m['month']

        # Get all dates in this month with data
        dates_in_month = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
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

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def index(request):
    return HttpResponse("Hello from Admin app")

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_login(request):
    from .login_attempts import is_locked_out, record_failed_attempt, clear_attempts, get_lockout_time_remaining
    
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        if is_locked_out(username, 'admin'):
            messages.error(request, "Account locked. Try again in 5 minutes.")
            return render(request, "adminLogin.html")

        try:
            admin = Admin.objects.get(username=username)
            if admin.password == password:  # 
                clear_attempts(username, 'admin')
                request.session["admin_id"] = admin.admin_id
                return redirect("adminpanel:admin_dashboard")  
            else:
                attempts = record_failed_attempt(username, 'admin')
                if attempts >= 5:
                    messages.error(request, "Account locked for 5 minutes due to multiple failed attempts.")
                elif attempts >= 2:
                    remaining = 5 - attempts
                    messages.error(request, f"Invalid password. {remaining} attempts remaining.")
                else:
                    messages.error(request, "Invalid password")
        except Admin.DoesNotExist:
            attempts = record_failed_attempt(username, 'admin')
            if attempts >= 5:
                messages.error(request, "Account locked for 5 minutes due to multiple failed attempts.")
            elif attempts >= 2:
                remaining = 5 - attempts
                messages.error(request, f"Invalid password. {remaining} attempts remaining.")
            else:
                messages.error(request, "Invalid password")

    return render(request, "adminLogin.html")


@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_dashboard(request):
    from django.db.models import Max
    from django.db.models.functions import TruncDate, ExtractYear, ExtractMonth
    from datetime import date
    from datetime import datetime as dt

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
        if not selected_year:
            selected_year = str(dt.now().year)

    # Get all valid office ids from Office table
    valid_office_ids = get_valid_office_ids()

    # Year options: all years with data
    year_options = get_year_options(valid_office_ids)

    # Month options: all months with data
    month_options = get_month_options(valid_office_ids)

    # Day options: all days with data, or filtered by month/year if selected
    day_options = get_day_options(valid_office_ids, selected_month, selected_year)

    # Week options: filtered by selected month/year if available
    week_options = get_week_options(valid_office_ids, selected_month, selected_year)

    # Determine filter date range
    filter_kwargs, selected_date, level, selected_month, selected_year = determine_filter_level(selected_day, selected_month, selected_year, selected_week)
    
    # Auto-select latest day if no filters provided
    if not selected_day and selected_date:
        selected_day = selected_date.strftime('%m/%d/%Y')

    # Aggregate sums for total energy usage, cost estimate, and carbon emission from selected filter
    aggregates = EnergyRecord.objects.filter(**filter_kwargs).aggregate(
        total_energy_usage=Sum('total_energy_kwh'),
        total_cost_predicted=Sum('cost_estimate'),
        total_co2_emission=Sum('carbon_emission_kgco2')
    )

    # Calculate predicted CO2 emission based on filter level
    if level == 'month':
        # For month: predict based on current month's daily average
        current_year = int(selected_year)
        current_month = int(selected_month)
        from calendar import monthrange
        _, days_in_month = monthrange(current_year, current_month)
        
        # Get days with data so far in the month
        days_with_data = EnergyRecord.objects.filter(
            date__year=current_year, date__month=current_month,
            device__office__office_id__in=valid_office_ids
        ).exclude(device__office__name='DS').dates('date', 'day').count()
        
        if days_with_data > 0:
            daily_avg = (aggregates['total_co2_emission'] or 0) / days_with_data
            predicted_co2_emission = daily_avg * days_in_month
        else:
            predicted_co2_emission = aggregates['total_co2_emission'] or 0
    else:
        # Default prediction for other levels
        predicted_co2_emission = (aggregates['total_co2_emission'] or 0) * 2

    # Prepare dates for display based on filter level
    if level == 'month':
        current_year = int(selected_year)
        current_month = int(selected_month)
        current_date = date(current_year, current_month, 1).strftime("%B %Y")
        from calendar import monthrange
        _, last_day = monthrange(current_year, current_month)
        predicted_date = date(current_year, current_month, last_day).strftime("%B %d, %Y")
    elif selected_date:
        current_date = selected_date.strftime("%B %d, %Y")
        predicted_date = (dt.combine(selected_date, dt.min.time()) + timedelta(days=7)).strftime("%B %d, %Y")
    else:
        current_date = datetime.now().strftime("%B %d, %Y")
        predicted_date = (datetime.now() + timedelta(days=7)).strftime("%B %d, %Y")

    # Aggregate energy usage per office from selected filter
    from django.db.models import F

    office_energy_qs = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).values(
        office_id=F('device__office__office_id'),
        office_name=F('device__office__name')
    ).annotate(
        total_energy=Sum('total_energy_kwh')
    ).order_by('-total_energy')

    # Get thresholds for the selected date and scale based on level
    base_thresholds = get_threshold_for_date(selected_date or datetime.now().date())
    threshold_values = get_scaled_thresholds(base_thresholds, level)
    energy_efficient_max = threshold_values['energy_efficient_max']
    energy_moderate_max = threshold_values['energy_moderate_max']

    # Determine status based on total_energy thresholds
    active_alerts = []
    for record in office_energy_qs:
        # Skip office with name exactly 'DS' or empty to remove duplicate entry
        if record['office_name'] == 'DS' or not record['office_name']:
            continue
        energy = record['total_energy'] or 0
        if energy > energy_moderate_max:
            status = 'High'
        elif energy > energy_efficient_max:
            status = 'Moderate'
        else:
            status = 'Efficient'
        active_alerts.append({
            'office_name': record['office_name'],
            'energy_usage': energy,
            'status': status
        })

    # Calculate progress percentage for CO2 emission bar
    co2_emission_progress = 0
    if predicted_co2_emission > 0:
        co2_emission_progress = min(100, (aggregates['total_co2_emission'] or 0) / predicted_co2_emission * 100)

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
        
        current_cost = EnergyRecord.objects.filter(
            date__year=current_year, date__month=current_month,
            device__office__office_id__in=valid_office_ids
        ).exclude(device__office__name='DS').aggregate(total=Sum('cost_estimate'))['total'] or 0
        
        prev_cost = EnergyRecord.objects.filter(
            date__year=prev_year, date__month=prev_month,
            device__office__office_id__in=valid_office_ids
        ).exclude(device__office__name='DS').aggregate(total=Sum('cost_estimate'))['total'] or 0
        
        change_costs = [prev_cost, current_cost]
        change_dates = [date(prev_year, prev_month, 1), date(current_year, current_month, 1)]
    elif selected_date:
        # Compare selected_date and previous day
        previous_date = selected_date - timedelta(days=1)
        change_dates = [previous_date, selected_date]
        change_costs = []
        for d in change_dates:
            cost = EnergyRecord.objects.filter(
                date=d, device__office__office_id__in=valid_office_ids
            ).exclude(device__office__name='DS').aggregate(total=Sum('cost_estimate'))['total'] or 0
            change_costs.append(cost)
    else:
        # Default to last two days with data
        change_dates_qs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(device__office__name='DS').dates('date', 'day').distinct().order_by('-date')[:2]
        change_dates = list(change_dates_qs)
        change_costs = []
        for d in change_dates:
            cost = EnergyRecord.objects.filter(
                date=d, device__office__office_id__in=valid_office_ids
            ).exclude(device__office__name='DS').aggregate(total=Sum('cost_estimate'))['total'] or 0
            change_costs.append(cost)

    if len(change_costs) >= 2:
        latest_cost = change_costs[1]  # selected_date or latest
        prev_cost = change_costs[0]  # previous
        if prev_cost > 0:
            change_percent = ((latest_cost - prev_cost) / prev_cost) * 100
        else:
            change_percent = 0
        is_decrease = change_percent < 0
        change_percent_abs = abs(change_percent)
        # Heights: scale to max
        max_cost = max(change_costs)
        heights = [(c / max_cost * 100) if max_cost > 0 else 0 for c in change_costs]
        if level == 'month':
            bar1_label = change_dates[0].strftime('%B %Y')  # previous month
            bar2_label = change_dates[1].strftime('%B %Y')  # current month
        else:
            bar1_label = change_dates[0].strftime('%B %d')  # previous day
            bar2_label = change_dates[1].strftime('%B %d')  # current day
            
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
    else:
        change_data = None

    context = {
        'total_energy_usage': aggregates['total_energy_usage'] or 0,
        'total_cost_predicted': aggregates['total_cost_predicted'] or 0,
        'total_co2_emission': aggregates['total_co2_emission'] or 0,
        'predicted_co2_emission': predicted_co2_emission,
        'current_date': current_date,
        'predicted_date': predicted_date,
        'co2_emission_progress': co2_emission_progress,
        'active_alerts': active_alerts,
        'change_data': change_data,
        'day_options': day_options,
        'month_options': month_options,
        'year_options': year_options,
        'week_options': week_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_week': selected_week,
        'level': level,
        'random_energy_tip': get_random_energy_tip(),
    }
    return render(request, 'adminDashboard.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_setting(request):
    offices = Office.objects.all()
    devices = Device.objects.select_related('office').all()
    
    energy_threshold = EnergyThreshold.objects.filter(ended_at__isnull=True).first()
    co2_threshold = CO2Threshold.objects.filter(ended_at__isnull=True).first()
    
    class ThresholdData:
        def __init__(self, energy, co2):
            self.energy_efficient_max = energy.efficient_max if energy else 10.0
            self.energy_moderate_max = energy.moderate_max if energy else 20.0
            self.energy_high_max = energy.high_max if energy else 30.0
            self.co2_efficient_max = co2.efficient_max if co2 else 8.0
            self.co2_moderate_max = co2.moderate_max if co2 else 13.0
            self.co2_high_max = co2.high_max if co2 else 18.0
    
    threshold = ThresholdData(energy_threshold, co2_threshold)
    energy_history = EnergyThreshold.objects.all().order_by('-created_at')[:10]
    co2_history = CO2Threshold.objects.all().order_by('-created_at')[:10]
    
    return render(request, 'adminSetting.html', {
        'offices': offices, 
        'devices': devices, 
        'threshold': threshold,
        'energy_history': energy_history,
        'co2_history': co2_history,
        'random_energy_tip': get_random_energy_tip(),
    })

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def office_usage(request):
    from django.db.models import Max, Min
    from django.db.models.functions import TruncDay, ExtractYear, ExtractMonth
    from django.utils import timezone
    from datetime import timedelta, date
    from datetime import datetime as dt

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')
    
    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
        if not selected_year:
            selected_year = str(dt.now().year)

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Year options: all years with data
    years_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    year_options = [str(y) for y in years_with_data]

    # Month options: all months with data
    months_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')
    
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    month_options = [{'value': str(m), 'name': month_names[m-1]} for m in months_with_data]

    # Day options: all days with data, or filtered by month/year if selected
    if selected_month and selected_year:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]
    else:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]

    # Week options: filtered by selected month/year if available
    week_options = get_week_options(valid_office_ids, selected_month, selected_year)

    # Determine filter date range
    filter_kwargs, selected_date, level, selected_month, selected_year = determine_filter_level(selected_day, selected_month, selected_year, selected_week)
    
    # Auto-select latest day if no filters provided
    if not selected_day and selected_date:
        selected_day = selected_date.strftime('%m/%d/%Y')

    # Filter office_data for table and pie chart based on filter_kwargs
    office_data = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).values(
        office_name=F('device__office__name')
    ).annotate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate'),
        total_co2=Sum('carbon_emission_kgco2')
    ).order_by('-total_energy')

    # Get thresholds for the selected date and scale based on level
    base_thresholds = get_threshold_for_date(selected_date or datetime.now().date())
    threshold_values = get_scaled_thresholds(base_thresholds, level)
    energy_efficient_max = threshold_values['energy_efficient_max']
    energy_moderate_max = threshold_values['energy_moderate_max']

    table_data = []
    for record in office_data:
        energy = record['total_energy'] or 0
        if energy > energy_moderate_max:
            status = 'HIGH'
            status_class = 'high'
        elif energy > energy_efficient_max:
            status = 'MODERATE'
            status_class = 'moderate'
        else:
            status = 'EFFICIENT'
            status_class = 'efficient'

        table_data.append({
            'office': record['office_name'],
            'energy': f"{energy:.1f} kWh",
            'cost': f"₱{record['total_cost']:.2f}" if record['total_cost'] else '₱0.00',
            'co2': f"{record['total_co2']:.1f} kg" if record['total_co2'] else '0.0 kg',
            'status': status,
            'status_class': status_class
        })

    # Prepare data for pie chart (filtered by selected date)
    pie_labels = [record['office_name'] for record in office_data]
    pie_values = [record['total_energy'] or 0 for record in office_data]

    # Prepare data for line chart (filtered by selected period)
    import calendar
    if level == 'day':
        start_date = selected_date
        end_date = selected_date
    elif level == 'month':
        start_date = date(int(selected_year), int(selected_month), 1)
        end_date = date(int(selected_year), int(selected_month), calendar.monthrange(int(selected_year), int(selected_month))[1])
    elif level == 'year':
        start_date = date(int(selected_year), 1, 1)
        end_date = date(int(selected_year), 12, 31)
    elif level == 'week':
        week_date = date.fromisoformat(selected_week)
        start_date = week_date
        end_date = start_date + timedelta(days=6)
    else:
        # Default to latest date
        start_date = selected_date
        end_date = selected_date

    line_data = EnergyRecord.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(
        day_date=TruncDay('date')
    ).values(
        'day_date',
        office_name=F('device__office__name')
    ).annotate(
        total_energy=Sum('total_energy_kwh')
    ).order_by('day_date', 'office_name')

    # Group data by date and office
    date_dict = {}
    for item in line_data:
        date_key = item['day_date'].strftime('%Y-%m-%d')
        office = item['office_name']
        energy = item['total_energy'] or 0
        if date_key not in date_dict:
            date_dict[date_key] = {}
        date_dict[date_key][office] = energy

    # Generate dates for the range
    full_dates = []
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        full_dates.append(date_str)
        current_date += timedelta(days=1)
    dates = sorted(full_dates)

    # Get offices from line_data or fallback to office_data
    line_offices = set(item['office_name'] for item in line_data)
    if not line_offices:
        line_offices = set(record['office_name'] for record in office_data)
    offices = sorted(line_offices)

    # Prepare labels (day and date) for the range
    line_labels = []
    for date_str in dates:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        day_abbr = date_obj.strftime('%a')
        full_date = date_obj.strftime('%B %d, %Y')
        line_labels.append({'day': day_abbr, 'date': full_date})

    # Prepare datasets
    line_datasets = []
    colors = ["#3b82f6", "#f97316", "#8b5cf6", "#22c55e", "#ef4444"]
    color_index = 0
    for office in offices:
        data_points = []
        for date_str in dates:
            data_points.append(date_dict.get(date_str, {}).get(office, 0))
        line_datasets.append({
            'label': office,
            'data': data_points,
            'borderColor': colors[color_index % len(colors)],
            'fill': False
        })
        color_index += 1

    context = {
        'table_data': table_data,
        'pie_labels': json.dumps(pie_labels),
        'pie_values': json.dumps(pie_values),
        'line_labels': json.dumps(line_labels),
        'line_datasets': json.dumps(line_datasets),
        'day_options': day_options,
        'month_options': month_options,
        'year_options': year_options,
        'week_options': week_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_week': selected_week,
        'random_energy_tip': get_random_energy_tip(),
    }
    return render(request, 'officeUsage.html', context)

def generate_recommendation(office_data, energy_moderate_max, energy_efficient_max, filter_kwargs, valid_office_ids):
    """Generate summary recommendation for all offices"""
    high_usage_offices = [r for r in office_data if (r['total_energy'] or 0) > energy_moderate_max]
    moderate_usage_offices = [r for r in office_data if energy_efficient_max < (r['total_energy'] or 0) <= energy_moderate_max]
    efficient_offices = [r for r in office_data if (r['total_energy'] or 0) <= energy_efficient_max]
    
    if high_usage_offices:
        count = len(high_usage_offices)
        names = ', '.join([r['office_name'] for r in high_usage_offices[:3]])
        if count > 3:
            names += f" and {count - 3} more"
        return f"{count} office(s) exceeded threshold: {names}. Immediate action required: reduce peak loads, implement automated shutdowns, and conduct energy audits."
    
    if moderate_usage_offices:
        count = len(moderate_usage_offices)
        names = ', '.join([r['office_name'] for r in moderate_usage_offices[:3]])
        if count > 3:
            names += f" and {count - 3} more"
        return f"{count} office(s) approaching threshold: {names}. Implement preventive measures: optimize AC settings (24-26°C), turn off unused equipment during breaks."
    
    if efficient_offices:
        return f"All {len(efficient_offices)} office(s) operating efficiently. Continue current energy-saving practices and maintain regular monitoring."
    
    return "No data available for the selected period. Ensure devices are connected and transmitting data properly."

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_reports(request):
    from django.db.models import Max, Min, Sum
    from django.db.models.functions import TruncDay, ExtractYear, ExtractMonth
    from django.utils import timezone
    from datetime import timedelta, date
    from datetime import datetime as dt
    from django.db.models import F

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
        if not selected_year:
            selected_year = str(dt.now().year)

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Year options: all years with data
    years_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    year_options = [str(y) for y in years_with_data]

    # Month options: all months with data
    months_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')

    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    month_options = [{'value': str(m), 'name': month_names[m-1]} for m in months_with_data]

    # Day options: all days with data, or filtered by month/year if selected
    if selected_month and selected_year:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]
    else:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]

    # Week options: filtered by selected month/year if available
    week_options = get_week_options(valid_office_ids, selected_month, selected_year)

    # Determine filter date range
    filter_kwargs, selected_date, level, selected_month, selected_year = determine_filter_level(selected_day, selected_month, selected_year, selected_week)
    
    # Auto-select latest day if no filters provided
    if not selected_day and selected_date:
        selected_day = selected_date.strftime('%m/%d/%Y')

    # Filter data for selected filter
    office_data = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).values(
        office_name=F('device__office__name')
    ).annotate(
        total_energy=Sum('total_energy_kwh')
    ).order_by('-total_energy')

    # Total Energy Usage
    total_energy_usage = sum(record['total_energy'] or 0 for record in office_data)

    # Highest Usage Office
    highest_office = office_data.first()
    highest_usage_office = highest_office['office_name'] if highest_office and (highest_office['total_energy'] or 0) > 0 else 'NONE'

    # Inactive Offices (energy == 0)
    all_offices = set(Office.objects.filter(office_id__in=valid_office_ids).exclude(name='DS').values_list('name', flat=True))
    active_offices = set(record['office_name'] for record in office_data if record['total_energy'] and record['total_energy'] > 0)
    inactive_offices = list(all_offices - active_offices)
    inactive_offices_str = ', '.join(inactive_offices) if inactive_offices else 'NONE'

    # Get thresholds for the selected date and scale based on level
    base_thresholds = get_threshold_for_date(selected_date or datetime.now().date())
    threshold_values = get_scaled_thresholds(base_thresholds, level)
    energy_efficient_max = threshold_values['energy_efficient_max']
    energy_moderate_max = threshold_values['energy_moderate_max']

    # Best Performing Office (lowest energy, assuming Efficient < energy_efficient_max)
    best_office = None
    min_energy = float('inf')
    for record in office_data:
        energy = record['total_energy'] or 0
        if energy < min_energy and energy <= energy_efficient_max:
            min_energy = energy
            best_office = record['office_name']
    best_performing_office = best_office if best_office else 'NONE'

    # Chart data: labels and values for bar chart
    chart_labels = [record['office_name'] for record in office_data]
    chart_values = [record['total_energy'] or 0 for record in office_data]
    # Colors based on status (High red, Moderate yellow, Efficient green)
    colors = []
    statuses = []
    recommendations = []
    for record in office_data:
        energy = record['total_energy'] or 0
        office_name = record['office_name']
        if energy > energy_moderate_max:
            colors.append('#d9534f')  # red
            statuses.append('Above Threshold')
            # Get peak power for this office
            office_records = EnergyRecord.objects.filter(
                **filter_kwargs,
                device__office__name=office_name,
                device__office__office_id__in=valid_office_ids
            )
            peak_power = office_records.aggregate(peak=Max('peak_power_w'))['peak'] or 0
            excess_pct = ((energy - energy_moderate_max) / energy_moderate_max * 100) if energy_moderate_max > 0 else 0
            recommendations.append(f"{office_name} exceeded threshold by {excess_pct:.1f}% ({energy:.1f} kWh). Peak: {peak_power:.0f}W. Reduce peak load by staggering equipment usage.")
        elif energy > energy_efficient_max:
            colors.append('#f0ad4e')  # yellow
            statuses.append('Within Threshold')
            recommendations.append(f"{office_name} is approaching threshold with {energy:.1f} kWh. Implement energy-saving measures: turn off unused equipment, optimize AC (24-26°C).")
        else:
            colors.append('#5cb85c')  # green
            statuses.append('Below Threshold')
            recommendations.append(f"{office_name} is operating efficiently with {energy:.1f} kWh. Continue current practices and maintain regular monitoring.")

    # Generate dynamic recommendation
    recommendation = generate_recommendation(office_data, energy_moderate_max, energy_efficient_max, filter_kwargs, valid_office_ids)

    context = {
        'total_energy_usage': total_energy_usage,
        'highest_usage_office': highest_usage_office,
        'inactive_offices': inactive_offices_str,
        'best_performing_office': best_performing_office,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
        'chart_colors': json.dumps(colors),
        'statuses': json.dumps(statuses),
        'recommendations': json.dumps(recommendations),
        'energy_efficient_max': energy_efficient_max,
        'energy_moderate_max': energy_moderate_max,
        'day_options': day_options,
        'month_options': month_options,
        'year_options': year_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'random_energy_tip': get_random_energy_tip(),
        'recommendation': recommendation,
    }
    return render(request, 'adminReports.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_costs(request):
    from django.db.models import Sum, Max, Count
    from django.db.models.functions import TruncDate, ExtractYear, ExtractMonth
    from datetime import datetime, timedelta, date
    from django.utils import timezone

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')
    
    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
        if not selected_year:
            selected_year = str(datetime.now().year)

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Year options: all years with data
    years_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    year_options = [str(y) for y in years_with_data]

    # Month options: all months with data
    months_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')
    
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    month_options = [{'value': str(m), 'name': month_names[m-1]} for m in months_with_data]

    # Day options: all days with data, or filtered by month/year if selected
    if selected_month and selected_year:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]
    else:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]

    # Determine filter date range
    filter_kwargs, selected_date, level, selected_month, selected_year = determine_filter_level(selected_day, selected_month, selected_year, selected_week)

    # Auto-select latest day if no filters provided
    if not selected_day and selected_date:
        selected_day = selected_date.strftime('%m/%d/%Y')

    # Week options: filtered by selected month/year if available
    week_options = get_week_options(valid_office_ids, selected_month, selected_year)

    # Aggregate totals for selected filter
    aggregates = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate')
    )

    num_days = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).dates('date', 'day').distinct().count() or 1

    total_energy = aggregates['total_energy'] or 0
    total_cost = aggregates['total_cost'] or 0
    avg_daily_cost = total_cost / num_days if num_days > 0 else 0

    # Highest cost office
    office_costs = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).values(
        office_name=F('device__office__name')
    ).annotate(
        total_cost=Sum('cost_estimate')
    ).order_by('-total_cost')

    highest_office = office_costs.first()['office_name'] if office_costs and office_costs.first()['total_cost'] else 'NONE'

    # Calculate period start and end based on level
    now = timezone.now().date()
    if level == 'week':
        if selected_week:
            period_start = date.fromisoformat(selected_week)
        else:
            # Default to current week
            period_start = now - timedelta(days=now.weekday())
        period_end = period_start + timedelta(days=6)
    elif level == 'month':
        year = int(selected_year) if selected_year else datetime.now().year
        month = int(selected_month) if selected_month else datetime.now().month
        period_start = date(year, month, 1)
        from calendar import monthrange
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
        year = int(selected_year) if selected_year else datetime.now().year
        month = int(selected_month) if selected_month else datetime.now().month
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

    # Previous cost
    prev_cost = EnergyRecord.objects.filter(
        date__gte=prev_start,
        date__lte=prev_end,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    # So far cost
    so_far_end = min(period_end, now)
    so_far_cost = EnergyRecord.objects.filter(
        date__gte=period_start,
        date__lte=so_far_end,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

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

    # Chart data: based on selected filter
    from calendar import monthrange
    from django.db.models.functions import ExtractMonth

    if level == 'week':
        week_date = date.fromisoformat(selected_week)
        start_date = week_date
        end_date = start_date + timedelta(days=6)
        chart_dates = [start_date + timedelta(days=i) for i in range(7)]
        chart_labels = [f"{d.strftime('%a')}\n{d.strftime('%B %d')}" for d in chart_dates]
        chart_data = []
        for d in chart_dates:
            cost = EnergyRecord.objects.filter(
                date=d,
                device__office__office_id__in=valid_office_ids
            ).exclude(
                device__office__name='DS'
            ).aggregate(total=Sum('cost_estimate'))['total'] or 0
            chart_data.append(cost)
    elif level == 'month':
        year = int(selected_year) if selected_year else datetime.now().year
        month = int(selected_month) if selected_month else datetime.now().month
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        chart_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        chart_labels = [d.strftime('%d') for d in chart_dates]  # Day numbers
        chart_data = []
        for d in chart_dates:
            cost = EnergyRecord.objects.filter(
                date=d,
                device__office__office_id__in=valid_office_ids
            ).exclude(
                device__office__name='DS'
            ).aggregate(total=Sum('cost_estimate'))['total'] or 0
            chart_data.append(cost)
    elif level == 'year':
        # Aggregate by month
        monthly_data = EnergyRecord.objects.filter(
            date__year=int(selected_year),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).annotate(
            month=ExtractMonth('date')
        ).values('month').annotate(
            total_cost=Sum('cost_estimate')
        ).order_by('month')
        chart_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        chart_data = [0] * 12
        for item in monthly_data:
            chart_data[item['month'] - 1] = item['total_cost'] or 0
    else:  # day or default
        # Default to last 7 days costs
        chart_dates_desc = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').distinct().order_by('-date')[:7]
        chart_dates = list(reversed(chart_dates_desc))
        chart_labels = [d.strftime('%B %d') for d in chart_dates]
        chart_data = []
        for d in chart_dates:
            cost = EnergyRecord.objects.filter(
                date=d,
                device__office__office_id__in=valid_office_ids
            ).exclude(
                device__office__name='DS'
            ).aggregate(total=Sum('cost_estimate'))['total'] or 0
            chart_data.append(cost)

    # Labels for chart header
    if level == 'week':
        previous_label = f"Previous Week ({prev_start.strftime('%B %d')} - {prev_end.strftime('%d, %Y')})"
        period_label = f"Week ({period_start.strftime('%B %d')} - {period_end.strftime('%d, %Y')})"
    elif level == 'month':
        previous_label = f"{prev_start.strftime('%B %Y')} Total"
        period_label = f"{period_start.strftime('%B %Y')}"
    elif level == 'year':
        previous_label = f"{prev_year} Total"
        period_label = f"{selected_year}"
    else:  # day
        previous_label = f"{prev_start.strftime('%B %d, %Y')} Total"
        period_label = f"{period_start.strftime('%B %d, %Y')}"

    so_far_label = f"So Far This {level.capitalize()} ({period_label})"
    if level == 'week':
        predicted_label = f"Predicted This {level.capitalize()}"
    else:
        predicted_label = f"Predicted This {level.capitalize()} ({period_label})"
    savings_label = "Estimated Savings"

    context = {
        'total_energy': total_energy,
        'total_cost': total_cost,
        'avg_daily_cost': avg_daily_cost,
        'highest_office': highest_office,
        'previous_label': previous_label,
        'prev_cost': prev_cost,
        'so_far_label': so_far_label,
        'so_far_cost': so_far_cost,
        'predicted_label': predicted_label,
        'predicted_cost': predicted_cost,
        'savings_label': savings_label,
        'savings': savings,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'day_options': day_options,
        'month_options': month_options,
        'year_options': year_options,
        'week_options': week_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_week': selected_week,
        'level': level,
        'random_energy_tip': get_random_energy_tip(),
    }
    return render(request, 'adminCosts.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def carbon_emission(request):
    from django.db.models import Sum, Max
    from django.db.models.functions import TruncDate, ExtractYear, ExtractMonth
    from datetime import datetime, timedelta, date
    from calendar import monthrange
    from django.utils import timezone
    import json

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')
    
    # Force month filtering when month is selected
    if selected_month and not selected_day and not selected_week:
        if not selected_year:
            selected_year = str(datetime.now().year)

    # Get all valid office ids from Office table
    from greenwatts.users.models import Office
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Year options: all years with data
    years_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    year_options = [str(y) for y in years_with_data]

    # Month options: all months with data
    months_with_data = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')
    
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    month_options = [{'value': str(m), 'name': month_names[m-1]} for m in months_with_data]

    # Day options: all days with data, or filtered by month/year if selected
    if selected_month and selected_year:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]
    else:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')]

    # Determine filter date range
    filter_kwargs, selected_date, level, selected_month, selected_year = determine_filter_level(selected_day, selected_month, selected_year, selected_week)
    
    # Auto-select latest day if no filters provided
    if not selected_day and selected_date:
        selected_day = selected_date.strftime('%m/%d/%Y')
    
    # Get current date for calculations
    now = timezone.now().date()
    
    # Week options: filtered by selected month/year if available
    week_options = get_week_options(valid_office_ids, selected_month, selected_year)

    # Aggregates for selected filter
    aggregates = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate'),
        total_co2=Sum('carbon_emission_kgco2')
    )

    num_days = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).dates('date', 'day').distinct().count() or 1

    total_energy_kwh = aggregates['total_energy'] or 0
    total_cost = aggregates['total_cost'] or 0
    avg_daily_cost = total_cost / num_days if num_days > 0 else 0

    # Highest CO2 emission office
    highest_office_data = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).values(
        office_name=F('device__office__name')
    ).annotate(
        total_co2=Sum('carbon_emission_kgco2')
    ).order_by('-total_co2')

    highest_co2_office = highest_office_data.first()['office_name'] if highest_office_data and highest_office_data.first()['total_co2'] else 'NONE'

    # Determine previous period for comparison
    if level == 'week':
        if selected_week:
            period_start = date.fromisoformat(selected_week)
        else:
            period_start = now - timedelta(days=now.weekday())
        period_end = period_start + timedelta(days=6)
        prev_start = period_start - timedelta(days=7)
        prev_end = period_end - timedelta(days=7)
        previous_label = f"Previous Week ({prev_start.strftime('%B %d')} - {prev_end.strftime('%d, %Y')})"
        period_label = f"{period_start.strftime('%B %d')} - {period_end.strftime('%d, %Y')}"
    elif level == 'month':
        period_start = date(int(selected_year or now.year), int(selected_month or now.month), 1)
        _, last_day = monthrange(int(selected_year or now.year), int(selected_month or now.month))
        period_end = date(int(selected_year or now.year), int(selected_month or now.month), last_day)
        prev_year = int(selected_year or now.year)
        prev_month = int(selected_month or now.month) - 1
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        prev_start = date(prev_year, prev_month, 1)
        _, last_day_prev = monthrange(prev_year, prev_month)
        prev_end = date(prev_year, prev_month, last_day_prev)
        previous_label = f"{prev_start.strftime('%B %Y')} Total"
        period_label = f"{period_start.strftime('%B %Y')}"
    elif level == 'year':
        period_start = date(int(selected_year or now.year), 1, 1)
        period_end = date(int(selected_year or now.year), 12, 31)
        prev_start = date(int(selected_year or now.year) - 1, 1, 1)
        prev_end = date(int(selected_year or now.year) - 1, 12, 31)
        previous_label = f"{prev_start.year} Total"
        period_label = f"{selected_year or now.year}"
    else:  # day
        period_start = selected_date or now
        period_end = selected_date or now
        prev_start = period_start - timedelta(days=1)
        prev_end = period_end - timedelta(days=1)
        prev_month = prev_start.month
        prev_year = prev_start.year
        previous_label = f"{prev_start.strftime('%B %d, %Y')} Total"
        period_label = f"{period_start.strftime('%B %d, %Y')}"

    # Previous CO2
    prev_co2 = EnergyRecord.objects.filter(
        date__gte=prev_start,
        date__lte=prev_end,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # So far CO2
    so_far_end = min(period_end, now)
    so_far_co2 = EnergyRecord.objects.filter(
        date__gte=period_start,
        date__lte=so_far_end,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # Predicted CO2
    total_days = (period_end - period_start).days + 1
    days_so_far = (so_far_end - period_start).days + 1 if so_far_end >= period_start else 0
    if days_so_far > 0 and period_end > now:
        avg_daily_co2 = so_far_co2 / days_so_far
        predicted_co2 = avg_daily_co2 * total_days
    else:
        predicted_co2 = so_far_co2

    # Change in emissions
    if prev_co2 > 0:
        change_percent = ((so_far_co2 - prev_co2) / prev_co2) * 100
    else:
        change_percent = 0
    change_direction = '▲' if change_percent > 0 else '▼'
    change_class = 'red-arrow' if change_percent > 0 else 'green-arrow'

    # Chart data based on level
    if level == 'week':
        week_date = date.fromisoformat(selected_week)
        start_date = week_date
        end_date = start_date + timedelta(days=6)
        chart_dates = [start_date + timedelta(days=i) for i in range(7)]
        labels = [f"{d.strftime('%a')}\n{d.strftime('%B %d')}" for d in chart_dates]
        prev_month_data = []
        current_month_data = []
        for d in chart_dates:
            co2 = EnergyRecord.objects.filter(
                date=d,
                device__office__office_id__in=valid_office_ids
            ).exclude(
                device__office__name='DS'
            ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0
            # For week, assume current is the selected week, prev is previous week
            if d >= prev_start and d <= prev_end:
                prev_month_data.append(co2)
                current_month_data.append(0)
            else:
                prev_month_data.append(0)
                current_month_data.append(co2)
    elif level == 'month':
        start_date = date(int(selected_year or now.year), int(selected_month or now.month), 1)
        _, last_day = monthrange(int(selected_year or now.year), int(selected_month or now.month))
        end_date = date(int(selected_year or now.year), int(selected_month or now.month), last_day)
        chart_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        labels = [d.strftime('%d') for d in chart_dates]
        current_month_data = []
        for d in chart_dates:
            co2 = EnergyRecord.objects.filter(
                date=d,
                device__office__office_id__in=valid_office_ids
            ).exclude(
                device__office__name='DS'
            ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0
            current_month_data.append(co2)
        prev_month_data = [0] * len(chart_dates)
    elif level == 'year':
        # Aggregate by month
        monthly_data = EnergyRecord.objects.filter(
            date__year=int(selected_year or now.year),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).annotate(
            month=ExtractMonth('date')
        ).values('month').annotate(
            total_co2=Sum('carbon_emission_kgco2')
        ).order_by('month')
        labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        prev_month_data = [0] * 12
        current_month_data = [0] * 12
        for item in monthly_data:
            current_month_data[item['month'] - 1] = item['total_co2'] or 0
        # For year, prev is previous year
        prev_year_data = EnergyRecord.objects.filter(
            date__year=int(selected_year or now.year) - 1,
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).annotate(
            month=ExtractMonth('date')
        ).values('month').annotate(
            total_co2=Sum('carbon_emission_kgco2')
        ).order_by('month')
        for item in prev_year_data:
            prev_month_data[item['month'] - 1] = item['total_co2'] or 0
    else:  # day
        # Default to last 12 days
        chart_dates_desc = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').distinct().order_by('-date')[:12]
        chart_dates = list(reversed(chart_dates_desc))
        labels = [d.strftime('%B %d') for d in chart_dates]
        prev_month_data = []
        current_month_data = []
        for d in chart_dates:
            co2 = EnergyRecord.objects.filter(
                date=d,
                device__office__office_id__in=valid_office_ids
            ).exclude(
                device__office__name='DS'
            ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0
            if d.month == prev_month and d.year == prev_year:
                prev_month_data.append(co2)
                current_month_data.append(0)
            else:
                prev_month_data.append(0)
                current_month_data.append(co2)

    # Get CO2 threshold - use BASE (daily) thresholds for chart since we show daily data points
    base_thresholds = get_threshold_for_date(selected_date or datetime.now().date())
    co2_efficient_max = base_thresholds['co2_efficient_max']
    co2_moderate_max = base_thresholds['co2_moderate_max']
    co2_high_max = co2_moderate_max * 1.5
    threshold = co2_high_max

    total_co2 = aggregates['total_co2'] or 0
    avg_daily_co2 = total_co2 / num_days if num_days > 0 else 0

    so_far_label = f"So Far This {level.capitalize()} ({period_label})"
    if level == 'week':
        predicted_label = f"Predicted This {level.capitalize()}"
    else:
        predicted_label = f"Predicted This {level.capitalize()} ({period_label})"

    context = {
        'total_energy_kwh': round(total_energy_kwh, 1),
        'total_co2': f"{total_co2:.1f}",
        'avg_daily_co2': f"{avg_daily_co2:.1f}",
        'highest_co2_office': highest_co2_office,
        'previous_label': previous_label,
        'prev_co2': f"{prev_co2:.1f}",
        'so_far_label': so_far_label,
        'so_far_co2': f"{so_far_co2:.1f}",
        'predicted_label': predicted_label,
        'predicted_co2': f"{predicted_co2:.0f}",
        'change_percent': f"{abs(change_percent):.2f}%",
        'change_direction': change_direction,
        'change_class': change_class,
        'chart_labels': json.dumps(labels),
        'prev_month_data': json.dumps(prev_month_data),
        'current_month_data': json.dumps(current_month_data),
        'threshold': threshold,
        'co2_efficient_max': co2_efficient_max,
        'co2_moderate_max': co2_moderate_max,
        'co2_high_max': co2_high_max,
        'week_options': week_options,
        'month_options': month_options,
        'year_options': year_options,
        'day_options': day_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_week': selected_week,
        'random_energy_tip': get_random_energy_tip(),
    }
    return render(request, 'carbonEmission.html', context)

@admin_required
@csrf_exempt
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def create_office(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            name = data.get("name")
            location = data.get("location")
            email = data.get("email")
            username = data.get("username")
            password = data.get("password")
            department = data.get("department")

            # For simplicity, assign admin as the first admin in DB (adjust as needed)
            admin = Admin.objects.first()

            office = Office.objects.create_user(
                username=username,
                email=email,
                password=password,
                name=name,
                location=location,
                department=department,
                admin=admin
            )
            return JsonResponse({"status": "success", "message": "Office created successfully"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})

@admin_required
@csrf_exempt
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def create_device(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            installed_date = data.get("installed_date")
            status = data.get("status")
            office_id = data.get("office_id")

            from greenwatts.users.models import Office
            from ..sensors.models import Device

            office = Office.objects.get(office_id=office_id)

            device = Device(
                installed_date=installed_date,
                status=status,
                office=office
            )
            device.save()
            return JsonResponse({"status": "success", "message": "Device created successfully"})
        except Office.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Office not found"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})

@admin_required
@csrf_exempt
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def edit_office(request, id):
    try:
        office = Office.objects.get(office_id=id)
    except Office.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Office not found"})

    if request.method == "GET":
        office_data = {
            "id": office.office_id,
            "name": office.name,
            "location": office.location,
            "email": office.email,
            "username": office.username,
            # Do not return password in GET response for security
            "department": office.department,
        }
        return JsonResponse({"status": "success", "office": office_data})

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            office.name = data.get("name", office.name)
            office.location = data.get("location", office.location)
            office.email = data.get("email", office.email)
            office.username = data.get("username", office.username)
            new_password = data.get("password", "")
            if new_password:
                office.set_password(new_password)
            office.department = data.get("department", office.department)
            office.save()
            return JsonResponse({"status": "success", "message": "Office updated successfully"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})

@admin_required
@csrf_exempt
def save_thresholds(request):
    if request.method == 'GET':
        try:
            energy_threshold = EnergyThreshold.objects.filter(ended_at__isnull=True).first()
            co2_threshold = CO2Threshold.objects.filter(ended_at__isnull=True).first()
            
            return JsonResponse({
                'status': 'success',
                'threshold': {
                    'energy_efficient_max': energy_threshold.efficient_max if energy_threshold else 10.0,
                    'energy_moderate_max': energy_threshold.moderate_max if energy_threshold else 20.0,
                    'energy_high_max': energy_threshold.high_max if energy_threshold else 30.0,
                    'co2_efficient_max': co2_threshold.efficient_max if co2_threshold else 8.0,
                    'co2_moderate_max': co2_threshold.moderate_max if co2_threshold else 13.0,
                    'co2_high_max': co2_threshold.high_max if co2_threshold else 18.0,
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    elif request.method == 'POST':
        try:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = request.POST.dict()

            # Handle energy threshold
            if 'energy_efficient_max' in data or 'energy_moderate_max' in data or 'energy_high_max' in data:
                energy_efficient = float(data.get('energy_efficient_max', 10.0))
                energy_moderate = float(data.get('energy_moderate_max', 20.0))
                energy_high = float(data.get('energy_high_max', 30.0))
                
                EnergyThreshold.objects.filter(ended_at__isnull=True).update(ended_at=timezone.now())
                EnergyThreshold.objects.create(
                    efficient_max=energy_efficient,
                    moderate_max=energy_moderate,
                    high_max=energy_high
                )

            # Handle CO2 threshold
            if 'co2_efficient_max' in data or 'co2_moderate_max' in data or 'co2_high_max' in data:
                co2_efficient = float(data.get('co2_efficient_max', 8.0))
                co2_moderate = float(data.get('co2_moderate_max', 13.0))
                co2_high = float(data.get('co2_high_max', 18.0))
                
                CO2Threshold.objects.filter(ended_at__isnull=True).update(ended_at=timezone.now())
                CO2Threshold.objects.create(
                    efficient_max=co2_efficient,
                    moderate_max=co2_moderate,
                    high_max=co2_high
                )

            return JsonResponse({'status': 'success', 'message': 'Thresholds updated successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@admin_required
def get_days(request):
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    if not month or not year:
        return JsonResponse({'status': 'error', 'message': 'Month and year required'})
    
    try:
        valid_office_ids = set(Office.objects.values_list('office_id', flat=True))
        days = EnergyRecord.objects.filter(
            date__year=int(year),
            date__month=int(month),
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').order_by('-date')
        
        day_options = [d.strftime('%m/%d/%Y') for d in days]
        
        return JsonResponse({
            'status': 'success',
            'days': day_options
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def threshold_history(request):
    energy_history = EnergyThreshold.objects.all().order_by('-created_at')
    co2_history = CO2Threshold.objects.all().order_by('-created_at')
    return JsonResponse({
        'status': 'success',
        'energy_history': list(energy_history.values(
            'threshold_id',
            'efficient_max',
            'moderate_max',
            'high_max',
            'created_at',
            'ended_at'
        )),
        'co2_history': list(co2_history.values(
            'threshold_id',
            'efficient_max',
            'moderate_max',
            'high_max',
            'created_at',
            'ended_at'
        ))
    })

@admin_required
def get_weeks(request):
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    try:
        valid_office_ids = get_valid_office_ids()
        week_options = get_week_options(valid_office_ids, month, year)
        
        return JsonResponse({
            'status': 'success',
            'weeks': week_options
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def export_reports(request):
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    
    valid_office_ids = get_valid_office_ids()
    filter_kwargs, selected_date, level, selected_month, selected_year = determine_filter_level(selected_day, selected_month, selected_year, None)
    
    office_data = EnergyRecord.objects.filter(**filter_kwargs).filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).values(
        office_name=F('device__office__name')
    ).annotate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate'),
        total_co2=Sum('carbon_emission_kgco2')
    ).order_by('-total_energy')
    
    response = HttpResponse(content_type='text/csv')
    filename = f"energy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['Office Name', 'Energy Usage (kWh)', 'Cost Estimate (PHP)', 'CO2 Emission (kg)'])
    
    for record in office_data:
        writer.writerow([
            record['office_name'],
            f"{record['total_energy']:.2f}" if record['total_energy'] else '0.00',
            f"{record['total_cost']:.2f}" if record['total_cost'] else '0.00',
            f"{record['total_co2']:.2f}" if record['total_co2'] else '0.00'
        ])
    
    return response

def admin_logout(request):
    request.session.flush()  # Clear the session
    response = redirect('users:index')  # Redirect to the landing page
    # Add cache control headers to prevent caching and back button navigation
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response