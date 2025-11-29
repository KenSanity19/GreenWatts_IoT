from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.views.decorators.cache import cache_control
from functools import wraps
from .models import Admin, Threshold
from greenwatts.users.models import Office
from ..sensors.models import Device
from ..sensors.models import EnergyRecord
from django.db.models import Sum, F
from datetime import datetime, timedelta
import json

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

def get_week_options(valid_office_ids):
    from django.db.models import Min
    from django.db.models.functions import ExtractYear, ExtractMonth

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
                messages.error(request, f"User does not exist. {remaining} attempts remaining.")
            else:
                messages.error(request, "User does not exist")

    return render(request, "adminLogin.html")


@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_dashboard(request):
    from django.db.models import Max
    from django.db.models.functions import TruncDate
    from datetime import date
    from datetime import datetime as dt

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Week options: fixed weeks for October 2025
    week_options = get_week_options(valid_office_ids)

    # Year options: only 2025
    year_options = ['2025']

    # Month options: only October
    month_options = [{'value': '10', 'name': 'October'}]

    # Day options: all 31 days in October 2025, formatted as mm/dd/yyyy
    from datetime import date, timedelta
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    day_options = []
    current = start_date
    while current <= end_date:
        day_options.append(current.strftime('%m/%d/%Y'))
        current += timedelta(days=1)

    # Determine filter date range
    filter_kwargs = {}
    selected_date = None
    level = 'day'
    if selected_day:
        try:
            month_str, day_str, year_str = selected_day.split('/')
            selected_date = date(int(year_str), int(month_str), int(day_str))
            filter_kwargs = {'date': selected_date}
            level = 'day'
            # Set selected_month and selected_year for template selects
            selected_month = month_str
            selected_year = year_str
        except ValueError:
            selected_date = None
    elif selected_month and selected_year:
        filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
        level = 'month'
    elif selected_year:
        filter_kwargs = {'date__year': int(selected_year)}
        level = 'year'
    elif selected_week:
        try:
            week_date = date.fromisoformat(selected_week)
            week_num = week_date.isocalendar()[1]
            filter_kwargs = {'date__week': week_num, 'date__year': week_date.year}
            level = 'week'
        except ValueError:
            selected_week = None
    else:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date
            filter_kwargs = {'date': selected_date}
            level = 'day'

    # Aggregate sums for total energy usage, cost estimate, and carbon emission from selected filter
    aggregates = EnergyRecord.objects.filter(**filter_kwargs).aggregate(
        total_energy_usage=Sum('total_energy_kwh'),
        total_cost_predicted=Sum('cost_estimate'),
        total_co2_emission=Sum('carbon_emission_kgco2')
    )

    # Calculate predicted CO2 emission (simple projection: current emission * 10 as example)
    predicted_co2_emission = (aggregates['total_co2_emission'] or 0) * 10

    # Prepare dates for display
    if selected_date:
        current_date = selected_date.strftime("%B %d, %Y")
    else:
        current_date = datetime.now().strftime("%B %d, %Y")
    predicted_date = (dt.combine(selected_date, dt.min.time()) + timedelta(days=7)).strftime("%B %d, %Y") if selected_date else (datetime.now() + timedelta(days=7)).strftime("%B %d, %Y")

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

    # Get thresholds from DB
    try:
        threshold = Threshold.objects.get(threshold_id=1)
        energy_efficient_max = threshold.energy_efficient_max
        energy_moderate_max = threshold.energy_moderate_max
    except Threshold.DoesNotExist:
        # Default values if not set
        energy_efficient_max = 10.0
        energy_moderate_max = 20.0

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

    # Change in cost data - filter consistently
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))
    if selected_date:
        # Compare selected_date and previous day
        previous_date = selected_date - timedelta(days=1)
        change_dates = [previous_date, selected_date]
    else:
        # Default to last two days with data
        change_dates_qs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').distinct().order_by('-date')[:2]
        change_dates = list(change_dates_qs)
    change_costs = []
    for d in change_dates:
        cost = EnergyRecord.objects.filter(
            date=d,
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(total=Sum('cost_estimate'))['total'] or 0
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
        change_data = {
            'bar1_label': change_dates[0].strftime('%B %d'),  # previous
            'bar1_height': heights[0],
            'bar2_label': change_dates[1].strftime('%B %d'),  # selected or latest
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
    }
    return render(request, 'adminDashboard.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_setting(request):
    offices = Office.objects.all()
    devices = Device.objects.select_related('office').all()
    try:
        threshold = Threshold.objects.get(threshold_id=1)
    except Threshold.DoesNotExist:
        threshold = None
    return render(request, 'adminSetting.html', {'offices': offices, 'devices': devices, 'threshold': threshold})

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def office_usage(request):
    from django.db.models import Max, Min
    from django.db.models.functions import TruncDay
    from django.utils import timezone
    from datetime import timedelta, date
    from datetime import datetime as dt

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Week options: last 4 weeks with data
    week_options = get_week_options(valid_office_ids)

    # Year options: only 2025
    year_options = ['2025']

    # Month options: only October
    month_options = [{'value': '10', 'name': 'October'}]

    # Day options: all 31 days in October 2025, formatted as mm/dd/yyyy
    from datetime import date, timedelta
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    day_options = []
    current = start_date
    while current <= end_date:
        day_options.append(current.strftime('%m/%d/%Y'))
        current += timedelta(days=1)

    # Determine filter date range
    filter_kwargs = {}
    selected_date = None
    level = 'day'
    if selected_day:
        try:
            month_str, day_str, year_str = selected_day.split('/')
            selected_date = date(int(year_str), int(month_str), int(day_str))
            filter_kwargs = {'date': selected_date}
            level = 'day'
            # Set selected_month and selected_year for template selects
            selected_month = month_str
            selected_year = year_str
        except ValueError:
            selected_date = None
    elif selected_month and selected_year:
        filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
        level = 'month'
    elif selected_year:
        filter_kwargs = {'date__year': int(selected_year)}
        level = 'year'
    elif selected_week:
        try:
            week_date = date.fromisoformat(selected_week)
            week_num = week_date.isocalendar()[1]
            filter_kwargs = {'date__week': week_num, 'date__year': week_date.year}
            level = 'week'
        except ValueError:
            selected_week = None
    else:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date
            filter_kwargs = {'date': selected_date}
            level = 'day'

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

    # Get thresholds from DB
    try:
        threshold = Threshold.objects.get(threshold_id=1)
        energy_efficient_max = threshold.energy_efficient_max
        energy_moderate_max = threshold.energy_moderate_max
    except Threshold.DoesNotExist:
        # Default values if not set
        energy_efficient_max = 10.0
        energy_moderate_max = 20.0

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
    }
    return render(request, 'officeUsage.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_reports(request):
    from django.db.models import Max, Min, Sum
    from django.db.models.functions import TruncDay
    from django.utils import timezone
    from datetime import timedelta, date
    from datetime import datetime as dt
    from django.db.models import F

    # Get selected day, month, year from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Year options: only 2025
    year_options = ['2025']

    # Month options: only October
    month_options = [{'value': '10', 'name': 'October'}]

    # Day options: all 31 days in October 2025, formatted as mm/dd/yyyy
    from datetime import date, timedelta
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    day_options = []
    current = start_date
    while current <= end_date:
        day_options.append(current.strftime('%m/%d/%Y'))
        current += timedelta(days=1)

    # Determine filter date range
    filter_kwargs = {}
    selected_date = None
    if selected_day:
        try:
            month_str, day_str, year_str = selected_day.split('/')
            selected_date = date(int(year_str), int(month_str), int(day_str))
            filter_kwargs = {'date': selected_date}
            # Set selected_month and selected_year for template selects
            selected_month = month_str
            selected_year = year_str
        except ValueError:
            selected_date = None
    elif selected_month and selected_year:
        filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
    elif selected_year:
        filter_kwargs = {'date__year': int(selected_year)}
    else:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date
            filter_kwargs = {'date': selected_date}

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

    # Get thresholds from DB
    try:
        threshold = Threshold.objects.get(threshold_id=1)
        energy_efficient_max = threshold.energy_efficient_max
    except Threshold.DoesNotExist:
        energy_efficient_max = 10.0

    # Best Performing Office (lowest energy, assuming Efficient < energy_efficient_max)
    best_office = None
    min_energy = float('inf')
    for record in office_data:
        energy = record['total_energy'] or 0
        if energy < min_energy and energy <= energy_efficient_max:
            min_energy = energy
            best_office = record['office_name']
    best_performing_office = best_office if best_office else 'NONE'

    # Get thresholds from DB
    try:
        threshold = Threshold.objects.get(threshold_id=1)
        energy_efficient_max = threshold.energy_efficient_max
        energy_moderate_max = threshold.energy_moderate_max
    except Threshold.DoesNotExist:
        energy_efficient_max = 10.0
        energy_moderate_max = 20.0

    # Chart data: labels and values for bar chart
    chart_labels = [record['office_name'] for record in office_data]
    chart_values = [record['total_energy'] or 0 for record in office_data]
    # Colors based on status (High red, Moderate yellow, Efficient green)
    colors = []
    statuses = []
    for record in office_data:
        energy = record['total_energy'] or 0
        if energy > energy_moderate_max:
            colors.append('#d9534f')  # red
            statuses.append('Above Threshold')
        elif energy > energy_efficient_max:
            colors.append('#f0ad4e')  # yellow
            statuses.append('Within Threshold')
        else:
            colors.append('#5cb85c')  # green
            statuses.append('Below Threshold')

    context = {
        'total_energy_usage': total_energy_usage,
        'highest_usage_office': highest_usage_office,
        'inactive_offices': inactive_offices_str,
        'best_performing_office': best_performing_office,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
        'chart_colors': json.dumps(colors),
        'statuses': json.dumps(statuses),
        'day_options': day_options,
        'month_options': month_options,
        'year_options': year_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
    }
    return render(request, 'adminReports.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_costs(request):
    from django.db.models import Sum, Max, Count
    from django.db.models.functions import TruncDate
    from datetime import datetime, timedelta, date
    from django.utils import timezone

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Week options: dynamic from database
    week_options = get_week_options(valid_office_ids)

    # Year options: only 2025
    year_options = ['2025']

    # Month options: only October
    month_options = [{'value': '10', 'name': 'October'}]

    # Day options: all 31 days in October 2025, formatted as mm/dd/yyyy
    from datetime import date, timedelta
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    day_options = []
    current = start_date
    while current <= end_date:
        day_options.append(current.strftime('%m/%d/%Y'))
        current += timedelta(days=1)

    # Determine filter date range
    filter_kwargs = {}
    selected_date = None
    level = 'day'
    if selected_day:
        try:
            month_str, day_str, year_str = selected_day.split('/')
            selected_date = date(int(year_str), int(month_str), int(day_str))
            filter_kwargs = {'date': selected_date}
            level = 'day'
            # Set selected_month and selected_year for template selects
            selected_month = month_str
            selected_year = year_str
        except ValueError:
            selected_date = None
    elif selected_month and selected_year:
        filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
        level = 'month'
    elif selected_year:
        filter_kwargs = {'date__year': int(selected_year)}
        level = 'year'
    elif selected_week:
        try:
            week_date = date.fromisoformat(selected_week)
            week_num = week_date.isocalendar()[1]
            filter_kwargs = {'date__week': week_num, 'date__year': week_date.year}
            level = 'week'
        except ValueError:
            selected_week = None
    else:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date
            filter_kwargs = {'date': selected_date}
            level = 'day'

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
        period_start = date(int(selected_year), int(selected_month), 1)
        from calendar import monthrange
        _, last_day = monthrange(int(selected_year), int(selected_month))
        period_end = date(int(selected_year), int(selected_month), last_day)
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
        prev_year = int(selected_year)
        prev_month = int(selected_month) - 1
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
        start_date = date(int(selected_year), int(selected_month), 1)
        _, last_day = monthrange(int(selected_year), int(selected_month))
        end_date = date(int(selected_year), int(selected_month), last_day)
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
    }
    return render(request, 'adminCosts.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def carbon_emission(request):
    from django.db.models import Sum, Max
    from django.db.models.functions import TruncDate
    from datetime import datetime, timedelta, date
    from calendar import monthrange
    from django.utils import timezone
    import json

    # Get selected day, month, year, week from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    selected_week = request.GET.get('selected_week')

    # Get all valid office ids from Office table
    from greenwatts.users.models import Office
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Week options: dynamic from database
    week_options = get_week_options(valid_office_ids)

    # Year options: only 2025
    year_options = ['2025']

    # Month options: only October
    month_options = [{'value': '10', 'name': 'October'}]

    # Day options: all 31 days in October 2025, formatted as mm/dd/yyyy
    from datetime import date, timedelta
    start_date = date(2025, 10, 1)
    end_date = date(2025, 10, 31)
    day_options = []
    current = start_date
    while current <= end_date:
        day_options.append(current.strftime('%m/%d/%Y'))
        current += timedelta(days=1)

    # Determine filter date range
    filter_kwargs = {}
    selected_date = None
    level = 'month'  # Default to month for CO2
    now = timezone.now().date()
    if selected_day:
        try:
            month_str, day_str, year_str = selected_day.split('/')
            selected_date = date(int(year_str), int(month_str), int(day_str))
            filter_kwargs = {'date': selected_date}
            level = 'day'
            # Set selected_month and selected_year for template selects
            selected_month = month_str
            selected_year = year_str
        except ValueError:
            selected_date = None
    elif selected_month and selected_year:
        filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
        level = 'month'
    elif selected_year:
        filter_kwargs = {'date__year': int(selected_year)}
        level = 'year'
    elif selected_week:
        try:
            week_date = date.fromisoformat(selected_week)
            week_num = week_date.isocalendar()[1]
            filter_kwargs = {'date__week': week_num, 'date__year': week_date.year}
            level = 'week'
        except ValueError:
            selected_week = None
    else:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date
            filter_kwargs = {'date': selected_date}
            level = 'day'
            selected_month = str(selected_date.month)
            selected_year = str(selected_date.year)
        else:
            # Fallback to current month if no data
            filter_kwargs = {'date__year': now.year, 'date__month': now.month}
            level = 'month'
            selected_month = str(now.month)
            selected_year = str(now.year)

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

    # Get CO2 threshold from DB
    try:
        threshold_obj = Threshold.objects.get(threshold_id=1)
        threshold = threshold_obj.co2_high_max
        co2_efficient_max = threshold_obj.co2_efficient_max
        co2_moderate_max = threshold_obj.co2_moderate_max
        co2_high_max = threshold_obj.co2_high_max
    except Threshold.DoesNotExist:
        threshold = 180.0  # Default value if not set
        co2_efficient_max = 8.0
        co2_moderate_max = 13.0
        co2_high_max = 18.0

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
            threshold = Threshold.objects.get(threshold_id=1)
            return JsonResponse({
                'status': 'success',
                'threshold': {
                    'energy_efficient_max': threshold.energy_efficient_max,
                    'energy_moderate_max': threshold.energy_moderate_max,
                    'energy_high_max': threshold.energy_high_max,
                    'co2_efficient_max': threshold.co2_efficient_max,
                    'co2_moderate_max': threshold.co2_moderate_max,
                    'co2_high_max': threshold.co2_high_max,
                }
            })
        except Threshold.DoesNotExist:
            return JsonResponse({
                'status': 'success',
                'threshold': {
                    'energy_efficient_max': 10.0,
                    'energy_moderate_max': 20.0,
                    'energy_high_max': 30.0,
                    'co2_efficient_max': 8.0,
                    'co2_moderate_max': 13.0,
                    'co2_high_max': 18.0,
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    elif request.method == 'POST':
        try:
            # Try to parse as JSON first
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                # If not JSON, assume form data
                data = request.POST.dict()

            # Get or create the threshold instance (assuming single row)
            threshold, created = Threshold.objects.get_or_create(
                threshold_id=1,  # Use a fixed ID for single threshold record
                defaults={
                    'energy_efficient_max': 10.0,
                    'energy_moderate_max': 20.0,
                    'energy_high_max': 30.0,
                    'co2_efficient_max': 8.0,
                    'co2_moderate_max': 13.0,
                    'co2_high_max': 18.0,
                }
            )

            # Update only the provided fields
            if 'energy_efficient_max' in data and data['energy_efficient_max']:
                threshold.energy_efficient_max = float(data['energy_efficient_max'])
            if 'energy_moderate_max' in data and data['energy_moderate_max']:
                threshold.energy_moderate_max = float(data['energy_moderate_max'])
            if 'energy_high_max' in data and data['energy_high_max']:
                threshold.energy_high_max = float(data['energy_high_max'])
            if 'co2_efficient_max' in data and data['co2_efficient_max']:
                threshold.co2_efficient_max = float(data['co2_efficient_max'])
            if 'co2_moderate_max' in data and data['co2_moderate_max']:
                threshold.co2_moderate_max = float(data['co2_moderate_max'])
            if 'co2_high_max' in data and data['co2_high_max']:
                threshold.co2_high_max = float(data['co2_high_max'])

            threshold.save()

            return JsonResponse({'status': 'success', 'message': 'Thresholds updated successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

def admin_logout(request):
    request.session.flush()  # Clear the session
    response = redirect('users:index')  # Redirect to the landing page
    # Add cache control headers to prevent caching and back button navigation
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response