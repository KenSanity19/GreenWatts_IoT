from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.views.decorators.cache import cache_control
from functools import wraps
from .models import Admin
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

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def index(request):
    return HttpResponse("Hello from Admin app")

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        try:
            admin = Admin.objects.get(username=username)
            if admin.password == password:  # 
                request.session["admin_id"] = admin.admin_id
                return redirect("adminpanel:admin_dashboard")  
            else:
                messages.error(request, "Invalid password")
        except Admin.DoesNotExist:
            messages.error(request, "User does not exist")

    return render(request, "adminLogin.html")


@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_dashboard(request):
    from django.db.models import Max
    from django.db.models.functions import TruncDate
    from datetime import date
    from datetime import datetime as dt

    # Get selected day, month, year from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')

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
    if selected_day and selected_month and selected_year:
        try:
            selected_date = date(int(selected_year), int(selected_month), int(selected_day))
            filter_kwargs = {'date': selected_date}
            level = 'day'
        except ValueError:
            selected_date = None
    elif selected_month and selected_year:
        filter_kwargs = {'date__year': int(selected_year), 'date__month': int(selected_month)}
        level = 'month'
    elif selected_year:
        filter_kwargs = {'date__year': int(selected_year)}
        level = 'year'
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
    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

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

    # Determine status based on total_energy thresholds
    active_alerts = []
    for record in office_energy_qs:
        # Skip office with name exactly 'DS' or empty to remove duplicate entry
        if record['office_name'] == 'DS' or not record['office_name']:
            continue
        energy = record['total_energy'] or 0
        if energy > 20:
            status = 'High'
        elif energy > 10:
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
        latest_cost = change_costs[0]
        prev_cost = change_costs[1]
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
            'bar1_label': change_dates[1].strftime('%B %d'),  # previous
            'bar1_height': heights[1],
            'bar2_label': change_dates[0].strftime('%B %d'),  # latest
            'bar2_height': heights[0],
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
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'level': level,
    }
    return render(request, 'adminDashboard.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_setting(request):
    offices = Office.objects.all()
    devices = Device.objects.select_related('office').all()
    return render(request, 'adminSetting.html', {'offices': offices, 'devices': devices})

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def office_usage(request):
    from django.db.models import Max, Min
    from django.db.models.functions import TruncDay
    from django.utils import timezone
    from datetime import timedelta, date
    from datetime import datetime as dt

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Get unique dates from EnergyRecord, last 7 days with data, ordered descending
    unique_dates_qs = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).dates('date', 'day').distinct().order_by('-date')[:7]
    day_options = [d.strftime('%m/%d/%Y') for d in unique_dates_qs]

    # Get selected date from request or use latest
    selected_date_str = request.GET.get('selected_date')
    selected_date = None
    if selected_date_str and selected_date_str in day_options:
        # Parse the selected date (format mm/dd/yyyy)
        try:
            month, day, year = map(int, selected_date_str.split('/'))
            selected_date = date(year, month, day)
        except ValueError:
            selected_date = None
    if not selected_date:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date

    # Filter office_data for table and pie chart based on selected date
    if selected_date:
        office_data = EnergyRecord.objects.filter(
            date=selected_date,
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
    else:
        office_data = EnergyRecord.objects.filter(
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

    table_data = []
    for record in office_data:
        energy = record['total_energy'] or 0
        if energy > 20:
            status = 'HIGH'
            status_class = 'high'
        elif energy > 10:
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

    # Prepare data for line chart (unchanged: based on available data range, weekly)
    # Get min and max dates from the database
    date_range = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )
    min_date = date_range['min_date']
    max_date = date_range['max_date']

    if min_date and max_date:
        # Ensure they are date objects
        if isinstance(min_date, timezone.datetime):
            min_date = min_date.date()
        if isinstance(max_date, timezone.datetime):
            max_date = max_date.date()
        # Use the full range of available data, up to 30 days max for chart readability
        date_diff = (max_date - min_date).days
        if date_diff > 30:
            start_date = max_date - timedelta(days=30)
        else:
            start_date = min_date
        end_date = max_date
    else:
        # Fallback if no data
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=7)

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
        'selected_date': selected_date_str if selected_date_str else None,
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

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Get unique dates from EnergyRecord, last 7 days with data, ordered descending
    unique_dates_qs = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).dates('date', 'day').distinct().order_by('-date')[:7]
    day_options = [d.strftime('%m/%d/%Y') for d in unique_dates_qs]

    # Get selected date from request or use latest
    selected_date_str = request.GET.get('selected_date')
    selected_date = None
    if selected_date_str and selected_date_str in day_options:
        # Parse the selected date (format mm/dd/yyyy)
        try:
            month, day, year = map(int, selected_date_str.split('/'))
            selected_date = date(year, month, day)
        except ValueError:
            selected_date = None
    if not selected_date:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date

    # Filter data for selected date
    if selected_date:
        office_data = EnergyRecord.objects.filter(
            date=selected_date,
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).values(
            office_name=F('device__office__name')
        ).annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('-total_energy')
    else:
        office_data = EnergyRecord.objects.filter(
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

    # Best Performing Office (lowest energy, assuming Efficient <10)
    best_office = None
    min_energy = float('inf')
    for record in office_data:
        energy = record['total_energy'] or 0
        if energy < min_energy and energy <= 10:  # Efficient threshold
            min_energy = energy
            best_office = record['office_name']
    best_performing_office = best_office if best_office else 'NONE'

    # Chart data: labels and values for bar chart
    chart_labels = [record['office_name'] for record in office_data]
    chart_values = [record['total_energy'] or 0 for record in office_data]
    # Colors based on status (High red, Moderate yellow, Efficient green)
    colors = []
    for record in office_data:
        energy = record['total_energy'] or 0
        if energy > 20:
            colors.append('#d9534f')  # red
        elif energy > 10:
            colors.append('#f0ad4e')  # yellow
        else:
            colors.append('#5cb85c')  # green

    context = {
        'total_energy_usage': total_energy_usage,
        'highest_usage_office': highest_usage_office,
        'inactive_offices': inactive_offices_str,
        'best_performing_office': best_performing_office,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
        'chart_colors': json.dumps(colors),
        'day_options': day_options,
        'selected_date': selected_date_str if selected_date_str else None,
    }
    return render(request, 'adminReports.html', context)

@admin_required
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_costs(request):
    from django.db.models import Sum, Max, Count
    from django.db.models.functions import TruncDate
    from datetime import datetime, timedelta, date
    from django.utils import timezone

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    # Get unique dates from EnergyRecord, last 7 days with data, ordered descending
    unique_dates_qs = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).dates('date', 'day').distinct().order_by('-date')[:7]
    day_options = [d.strftime('%m/%d/%Y') for d in unique_dates_qs]

    # Get selected date from request or use latest
    selected_date_str = request.GET.get('selected_date')
    selected_date = None
    if selected_date_str and selected_date_str in day_options:
        # Parse the selected date (format mm/dd/yyyy)
        try:
            month, day, year = map(int, selected_date_str.split('/'))
            selected_date = date(year, month, day)
        except ValueError:
            selected_date = None
    if not selected_date:
        # Default to latest date
        latest_date_qs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date

    # Aggregate totals for selected date or overall if no date
    if selected_date:
        aggregates = EnergyRecord.objects.filter(
            date=selected_date,
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(
            total_energy=Sum('total_energy_kwh'),
            total_cost=Sum('cost_estimate')
        )
        num_days = 1
    else:
        aggregates = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).aggregate(
            total_energy=Sum('total_energy_kwh'),
            total_cost=Sum('cost_estimate')
        )
        num_days = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).dates('date', 'day').distinct().count()

    total_energy = aggregates['total_energy'] or 0
    total_cost = aggregates['total_cost'] or 0
    avg_daily_cost = total_cost / num_days if num_days > 0 else 0

    # Highest cost office
    if selected_date:
        office_costs = EnergyRecord.objects.filter(
            date=selected_date,
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).values(
            office_name=F('device__office__name')
        ).annotate(
            total_cost=Sum('cost_estimate')
        ).order_by('-total_cost')
    else:
        office_costs = EnergyRecord.objects.filter(
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).values(
            office_name=F('device__office__name')
        ).annotate(
            total_cost=Sum('cost_estimate')
        ).order_by('-total_cost')

    highest_office = office_costs.first()['office_name'] if office_costs and office_costs.first()['total_cost'] else 'NONE'

    # For chart header: assume current month is the month of selected_date or current
    now = timezone.now().date()
    current_month = selected_date.month if selected_date else now.month
    current_year = selected_date.year if selected_date else now.year

    # June total (hardcoded as previous month, adjust)
    june_cost = EnergyRecord.objects.filter(
        date__year=current_year,
        date__month=6,  # June
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    # So far this month
    so_far_cost = EnergyRecord.objects.filter(
        date__year=current_year,
        date__month=current_month,
        date__lte=now,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    # Predicted this month: average daily * days in month
    days_in_month = (date(current_year, current_month + 1, 1) - date(current_year, current_month, 1)).days if current_month < 12 else 31
    avg_daily = so_far_cost / now.day if now.day > 0 else 0
    predicted_cost = avg_daily * days_in_month

    # Estimate savings: difference from previous month
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = current_year if current_month > 1 else current_year - 1
    prev_cost = EnergyRecord.objects.filter(
        date__year=prev_year,
        date__month=prev_month,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0
    savings = prev_cost - predicted_cost if prev_cost > predicted_cost else 0

    # Chart data: last 7 days costs
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

    context = {
        'total_energy': total_energy,
        'total_cost': total_cost,
        'avg_daily_cost': avg_daily_cost,
        'highest_office': highest_office,
        'june_cost': june_cost,
        'so_far_cost': so_far_cost,
        'predicted_cost': predicted_cost,
        'savings': savings,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'day_options': day_options,
        'selected_date': selected_date_str if selected_date_str else None,
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

    # Get all valid office ids from Office table
    from greenwatts.users.models import Office
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    now = timezone.now().date()
    current_month = now.month
    current_year = now.year
    days_so_far = now.day

    # Previous month
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = current_year if current_month > 1 else current_year - 1
    previous_month_name = date(prev_year, prev_month, 1).strftime('%B %Y')

    # Days in current month
    days_in_month = monthrange(current_year, current_month)[1]

    # Aggregates for current month so far
    current_month_aggregates = EnergyRecord.objects.filter(
        date__year=current_year,
        date__month=current_month,
        date__lte=now,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate'),
        total_co2=Sum('carbon_emission_kgco2')
    )

    total_energy_kwh = current_month_aggregates['total_energy'] or 0
    total_cost = current_month_aggregates['total_cost'] or 0
    avg_daily_cost = total_cost / days_so_far if days_so_far > 0 else 0

    # Highest CO2 emission office (current month)
    highest_office_data = EnergyRecord.objects.filter(
        date__year=current_year,
        date__month=current_month,
        date__lte=now,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).values(
        office_name=F('device__office__name')
    ).annotate(
        total_co2=Sum('carbon_emission_kgco2')
    ).order_by('-total_co2')

    highest_co2_office = highest_office_data.first()['office_name'] if highest_office_data else 'NONE'

    # Last month total CO2
    last_month_total_co2 = EnergyRecord.objects.filter(
        date__year=prev_year,
        date__month=prev_month,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # Current month so far CO2
    current_month_so_far_co2 = current_month_aggregates['total_co2'] or 0

    # Predicted this month CO2
    avg_daily_co2 = current_month_so_far_co2 / days_so_far if days_so_far > 0 else 0
    predicted_month_co2 = avg_daily_co2 * days_in_month

    # Change in emissions
    if last_month_total_co2 > 0:
        change_percent = ((current_month_so_far_co2 - last_month_total_co2) / last_month_total_co2) * 100
    else:
        change_percent = 0
    change_direction = '▲' if change_percent > 0 else '▼'
    change_class = 'red-arrow' if change_percent > 0 else 'green-arrow'  # Assume red for increase

    # Chart data: Last 40 days to cover two months
    end_date = now
    start_date = end_date - timedelta(days=40)
    daily_data = EnergyRecord.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).annotate(
        day_date=TruncDate('date')
    ).values(
        'day_date'
    ).annotate(
        total_co2=Sum('carbon_emission_kgco2')
    ).order_by('day_date')

    # Generate full date range
    date_range = []
    current = start_date
    while current <= end_date:
        date_range.append(current)
        current += timedelta(days=1)

    # Map data
    date_dict = {item['day_date']: item['total_co2'] or 0 for item in daily_data}
    daily_co2 = [date_dict.get(d, 0) for d in date_range]

    # Split into previous and current month data
    prev_month_data = []
    current_month_data = []
    labels = []
    for d in date_range:
        month_name = d.strftime('%B')
        label = f"{month_name} {d.day}"
        labels.append(label)

        if d.month == prev_month and d.year == prev_year:
            prev_month_data.append(date_dict.get(d, 0))
            current_month_data.append(0)
        else:
            prev_month_data.append(0)
            current_month_data.append(date_dict.get(d, 0))

    # Pad to 12 points if needed, but use actual
    # For now, use up to 12 recent points
    labels = labels[-12:]
    prev_month_data = prev_month_data[-12:]
    current_month_data = current_month_data[-12:]

    threshold = 180  # Fixed

    context = {
        'total_energy_kwh': round(total_energy_kwh, 1),
        'total_cost': f"{total_cost:.2f}",
        'avg_daily_cost': f"{avg_daily_cost:.2f}",
        'highest_co2_office': highest_co2_office,
        'last_month_co2': f"{last_month_total_co2:.1f}",
        'current_month_so_far_co2': f"{current_month_so_far_co2:.1f}",
        'predicted_month_co2': f"{predicted_month_co2:.0f}",
        'change_percent': f"{abs(change_percent):.2f}%",
        'change_direction': change_direction,
        'change_class': change_class,
        'chart_labels': json.dumps(labels),
        'prev_month_data': json.dumps(prev_month_data),
        'current_month_data': json.dumps(current_month_data),
        'threshold': threshold,
        'previous_month_name': previous_month_name,
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

def admin_logout(request):
    request.session.flush()  # Clear the session
    response = redirect('users:index')  # Redirect to the landing page
    # Add cache control headers to prevent caching and back button navigation
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response
