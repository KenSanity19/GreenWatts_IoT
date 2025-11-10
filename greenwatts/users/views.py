from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control

def index(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = auth.authenticate(username=username, password=password)
        if user is not None:
            auth.login(request, user)
            return redirect('users:dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
            return redirect('users:index')
    return render(request, 'index.html')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def dashboard(request):
    from django.db.models import Sum, Max
    from django.utils import timezone
    from datetime import timedelta, date
    from calendar import monthrange
    import json
    from ..sensors.models import EnergyRecord

    office = request.user
    selected_date_str = request.GET.get('selected_date')

    # Get devices for the user's office
    devices = office.devices.all()

    # Get unique dates for day options
    unique_dates_qs = EnergyRecord.objects.filter(device__in=devices).dates('date', 'day').distinct().order_by('-date')[:7]
    day_options = [d.strftime('%m/%d/%Y') for d in unique_dates_qs]

    if selected_date_str:
        try:
            # Parse mm/dd/yyyy format
            month, day, year = map(int, selected_date_str.split('/'))
            selected_date = date(year, month, day)
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        # Default to the latest date with data if available, else current date
        if day_options:
            latest_date_str = day_options[0]
            month, day, year = map(int, latest_date_str.split('/'))
            selected_date = date(year, month, day)
        else:
            selected_date = timezone.now().date()

    # Total energy usage for selected date
    energy_usage = EnergyRecord.objects.filter(
        device__in=devices,
        date=selected_date
    ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0

    # Cost predicted (assuming cost_estimate is the predicted cost)
    cost_predicted = EnergyRecord.objects.filter(
        device__in=devices,
        date=selected_date
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    # CO2 emissions for selected date
    co2_emissions = EnergyRecord.objects.filter(
        device__in=devices,
        date=selected_date
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # Active alerts: All devices' energy for selected date
    alerts_qs = EnergyRecord.objects.filter(
        device__in=devices,
        date=selected_date
    ).select_related('device').values('device__office__name', 'total_energy_kwh')

    active_alerts = []
    for record in alerts_qs:
        energy = record['total_energy_kwh'] or 0
        if energy > 20:
            status = 'High'
        elif energy > 10:
            status = 'Moderate'
        else:
            status = 'Efficient'
        active_alerts.append({
            'office_name': record['device__office__name'],
            'energy_usage': energy,
            'status': status
        })

    # Change in cost: Compare selected date and the previous day
    prev_date = selected_date - timedelta(days=1)
    selected_cost = EnergyRecord.objects.filter(device__in=devices, date=selected_date).aggregate(total=Sum('cost_estimate'))['total'] or 0
    prev_cost = EnergyRecord.objects.filter(device__in=devices, date=prev_date).aggregate(total=Sum('cost_estimate'))['total'] or 0

    if prev_cost > 0:
        change_percent = ((selected_cost - prev_cost) / prev_cost) * 100
    else:
        change_percent = 0
    is_decrease = change_percent < 0
    change_percent_abs = round(min(abs(change_percent), 100), 2)  # Cap at 100% and round to 2 decimal places
    max_cost = max(selected_cost, prev_cost) if selected_cost > 0 or prev_cost > 0 else 1
    heights = [(prev_cost / max_cost * 100) if max_cost > 0 else 0, (selected_cost / max_cost * 100) if max_cost > 0 else 0]
    change_data = {
        'bar1_label': prev_date.strftime('%B %d'),
        'bar1_height': heights[0],
        'bar2_label': selected_date.strftime('%B %d'),
        'bar2_height': heights[1],
        'percent': change_percent_abs,
        'type': 'DECREASE' if is_decrease else 'INCREASE',
        'arrow': 'down' if is_decrease else 'up',
        'color_class': 'decrease' if is_decrease else 'increase'
    }

    # Carbon footprint: Till date and predicted for the selected date's month
    selected_year = selected_date.year
    selected_month = selected_date.month
    days_so_far = selected_date.day
    days_in_month = monthrange(selected_year, selected_month)[1]

    month_so_far_co2 = EnergyRecord.objects.filter(
        device__in=devices,
        date__year=selected_year,
        date__month=selected_month,
        date__lte=selected_date
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    avg_daily_co2 = month_so_far_co2 / days_so_far if days_so_far > 0 else 0
    predicted_co2 = avg_daily_co2 * days_in_month

    # Calculate progress percentage for carbon footprint bar
    progress_percentage = (month_so_far_co2 / predicted_co2 * 100) if predicted_co2 > 0 else 0

    # Predicted date for carbon footprint
    predicted_date = selected_date + timedelta(days=7)

    context = {
        'office': office,
        'selected_date': selected_date,
        'predicted_date': predicted_date,
        'day_options': day_options,
        'energy_usage': f"{energy_usage:.2f}",
        'cost_predicted': f"₱{cost_predicted:.2f}",
        'co2_emissions': f"{co2_emissions:.2f}",
        'active_alerts': active_alerts,
        'change_data': change_data,
        'month_so_far_co2': f"{month_so_far_co2:.2f}",
        'predicted_co2': f"{predicted_co2:.2f}",
        'progress_percentage': f"{progress_percentage:.1f}",
    }
    return render(request, 'users/dashboard.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def office_usage(request):
    from django.db.models import Sum, F
    from django.utils import timezone
    from datetime import date
    from ..sensors.models import EnergyRecord

    office = request.user
    selected_date_str = request.GET.get('selected_date')

    # Get devices for the user's office
    devices = office.devices.all()

    # Get unique dates for day options
    unique_dates_qs = EnergyRecord.objects.filter(device__in=devices).dates('date', 'day').distinct().order_by('-date')[:7]
    day_options = [d.strftime('%m/%d/%Y') for d in unique_dates_qs]

    if selected_date_str:
        try:
            # Parse mm/dd/yyyy format
            month, day, year = map(int, selected_date_str.split('/'))
            selected_date = date(year, month, day)
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        # Default to the latest date with data if available, else current date
        if day_options:
            latest_date_str = day_options[0]
            month, day, year = map(int, latest_date_str.split('/'))
            selected_date = date(year, month, day)
        else:
            selected_date = timezone.now().date()

    # Filter data for selected date
    office_data = EnergyRecord.objects.filter(
        date=selected_date,
        device__in=devices
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

    context = {
        'office': office,
        'selected_date': selected_date_str if selected_date_str else None,
        'day_options': day_options,
        'table_data': table_data,
    }
    return render(request, 'users/userUsage.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def user_reports(request):
    from django.db.models import Sum, Max, Min
    from django.utils import timezone
    from datetime import timedelta, date
    import json
    from ..sensors.models import EnergyRecord

    office = request.user
    devices = office.devices.all()
    now = timezone.now().date()

    # Get min date from EnergyRecord to determine available weeks
    min_date_qs = EnergyRecord.objects.filter(device__in=devices).aggregate(min_date=Min('date'))
    min_date = min_date_qs['min_date']
    if not min_date:
        # No data, handle gracefully
        context = {
            'week_options': [],
            'selected_week': 1,
            'total_energy_usage': '0.00',
            'highest_usage_day': 'N/A',
            'cost_predicted': '₱0.00',
            'best_performing_day': 'N/A',
            'chart_labels': json.dumps([]),
            'chart_values': json.dumps([]),
            'recommendation': 'No data available.',
        }
        return render(request, 'users/userReports.html', context)

    # Generate week options: Weeks from min_date to now, labeled as Week 1, Week 2, etc.
    week_options = []
    current_week_start = min_date - timedelta(days=min_date.weekday())  # Monday of min_date week
    week_num = 1
    while current_week_start <= now:
        week_end = current_week_start + timedelta(days=6)
        week_options.append({
            'value': week_num,
            'label': f'Week {week_num}',
            'start_date': current_week_start,
            'end_date': week_end,
        })
        current_week_start += timedelta(days=7)
        week_num += 1

    # Reverse to have latest first, but keep numbering ascending
    week_options.reverse()

    # Get selected week from GET, default to latest (Week with highest num)
    selected_week_num = request.GET.get('week')
    if selected_week_num:
        try:
            selected_week_num = int(selected_week_num)
        except ValueError:
            selected_week_num = len(week_options)
    else:
        selected_week_num = len(week_options)  # Latest

    # Find selected week
    selected_week = next((w for w in week_options if w['value'] == selected_week_num), week_options[-1] if week_options else None)
    if not selected_week:
        selected_week = week_options[0] if week_options else None

    week_start = selected_week['start_date']
    week_end = selected_week['end_date']

    # Fetch data for the week
    week_data = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=week_start,
        date__lte=week_end
    ).values('date').annotate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate')
    ).order_by('date')

    # Prepare daily data for chart
    daily_energy = {}
    for record in week_data:
        daily_energy[record['date']] = record['total_energy'] or 0

    # Generate labels and values for the week
    chart_labels = []
    chart_values = []
    current = week_start
    while current <= week_end:
        chart_labels.append([current.strftime('%A'), current.strftime('%Y-%m-%d')])
        chart_values.append(daily_energy.get(current, 0))
        current += timedelta(days=1)

    # Total energy usage for the week
    total_energy_usage = sum(chart_values)

    # Highest usage day
    if chart_values:
        max_energy = max(chart_values)
        max_index = chart_values.index(max_energy)
        highest_usage_day = (week_start + timedelta(days=max_index)).strftime('%Y-%m-%d')
    else:
        highest_usage_day = 'N/A'
        max_energy = 0

    # Cost predicted for the week
    cost_predicted = sum(record['total_cost'] or 0 for record in week_data)

    # Best performing day (lowest usage)
    if chart_values:
        min_energy = min(chart_values)
        min_index = chart_values.index(min_energy)
        best_performing_day = (week_start + timedelta(days=min_index)).strftime('%Y-%m-%d')
    else:
        best_performing_day = 'N/A'

    # Recommendation based on highest usage day
    if max_energy > 20:
        recommendation = f"Usage exceeded on {highest_usage_day}. Consider reducing usage during peak hours."
    else:
        recommendation = "Energy usage is within acceptable limits. Keep up the good work!"

    context = {
        'office': office,
        'week_options': week_options,
        'selected_week': selected_week_num,
        'total_energy_usage': f"{total_energy_usage:.2f}",
        'highest_usage_day': highest_usage_day,
        'cost_predicted': f"₱{cost_predicted:.2f}",
        'best_performing_day': best_performing_day,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
        'recommendation': recommendation,
    }
    return render(request, 'users/userReports.html', context)



@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def user_energy_cost(request):
    from django.db.models import Sum, Min
    from django.utils import timezone
    from datetime import date, timedelta
    from ..sensors.models import EnergyRecord
    import json

    office = request.user
    devices = office.devices.all()
    now = timezone.now().date()

    # Get min date from EnergyRecord to determine available weeks
    min_date_qs = EnergyRecord.objects.filter(device__in=devices).aggregate(min_date=Min('date'))
    min_date = min_date_qs['min_date']
    if not min_date:
        # No data, handle gracefully
        context = {
            'week_options': [],
            'selected_week': 1,
            'last_month_cost': '₱0.00',
            'current_month_so_far_cost': '₱0.00',
            'predicted_total_cost': '₱0.00',
            'estimate_saving': '₱0.00',
            'chart_labels': json.dumps([]),
            'chart_data': json.dumps([]),
        }
        return render(request, 'users/userEnergyCost.html', context)

    # Generate week options: Weeks from min_date to now, labeled as Week 1, Week 2, etc.
    week_options = []
    current_week_start = min_date - timedelta(days=min_date.weekday())  # Monday of min_date week
    week_num = 1
    while current_week_start <= now:
        week_end = current_week_start + timedelta(days=6)
        week_options.append({
            'value': week_num,
            'label': f'Week {week_num}',
            'start_date': current_week_start,
            'end_date': week_end,
        })
        current_week_start += timedelta(days=7)
        week_num += 1

    # Reverse to have latest first, but keep numbering ascending
    week_options.reverse()

    # Get selected week from GET, default to latest (Week with highest num)
    selected_week_num = request.GET.get('week')
    if selected_week_num:
        try:
            selected_week_num = int(selected_week_num)
        except ValueError:
            selected_week_num = len(week_options)
    else:
        selected_week_num = len(week_options)  # Latest

    # Find selected week
    selected_week = next((w for w in week_options if w['value'] == selected_week_num), week_options[-1] if week_options else None)
    if not selected_week:
        selected_week = week_options[0] if week_options else None

    week_start = selected_week['start_date']
    week_end = selected_week['end_date']

    # Last month (relative to the selected week)
    last_month = week_start.replace(day=1) - timedelta(days=1)
    last_month_start = last_month.replace(day=1)
    last_month_end = last_month
    last_month_cost = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=last_month_start,
        date__lte=last_month_end
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    # Current month so far (relative to the selected week)
    current_month_start = week_start.replace(day=1)
    current_month_end = min(week_end, now)
    current_month_so_far_cost = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=current_month_start,
        date__lte=current_month_end
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    # Predicted total this month
    days_in_month = ((current_month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)).day
    days_so_far = (current_month_end - current_month_start).days + 1
    if days_so_far > 0:
        daily_avg = current_month_so_far_cost / days_so_far
        predicted_total_cost = daily_avg * days_in_month
    else:
        predicted_total_cost = 0

    # Estimate saving: compared to last month
    if last_month_cost > predicted_total_cost:
        estimate_saving = last_month_cost - predicted_total_cost
    else:
        estimate_saving = 0

    # Weekly chart: for the selected week
    week_data = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=week_start,
        date__lte=week_end
    ).values('date').annotate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate')
    ).order_by('date')

    # Calculate card data
    total_energy_sum = sum(record['total_energy'] or 0 for record in week_data)
    total_cost_sum = sum(record['total_cost'] or 0 for record in week_data)
    avg_daily_cost = total_cost_sum / 7 if total_cost_sum else 0
    if week_data:
        max_record = max(week_data, key=lambda x: x['total_cost'] or 0)
        highest_cost_day = max_record['date'].strftime('%Y-%m-%d')
    else:
        highest_cost_day = 'N/A'

    chart_labels = []
    chart_data = []
    current = week_start
    cost_dict = {record['date']: record['total_cost'] or 0 for record in week_data}

    while current <= week_end:
        chart_labels.append([current.strftime('%A'), current.strftime('%Y-%m-%d')])
        chart_data.append(cost_dict.get(current, 0))
        current += timedelta(days=1)

    context = {
        'office': office,
        'week_options': week_options,
        'selected_week': selected_week_num,
        'total_energy': f"{total_energy_sum:.2f}",
        'total_cost': f"₱{total_cost_sum:.2f}",
        'avg_daily_cost': f"₱{avg_daily_cost:.2f}",
        'highest_cost_day': highest_cost_day,
        'last_month_cost': f"₱{last_month_cost:.2f}",
        'current_month_so_far_cost': f"₱{current_month_so_far_cost:.2f}",
        'predicted_total_cost': f"₱{predicted_total_cost:.2f}",
        'estimate_saving': f"₱{estimate_saving:.2f}",
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'users/userEnergyCost.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def user_emmision(request):
    from django.db.models import Sum, Min
    from django.db.models.functions import TruncDate
    from datetime import datetime, timedelta, date
    from calendar import monthrange
    from django.utils import timezone
    import json
    from greenwatts.users.models import Office
    from ..sensors.models import EnergyRecord

    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    now = timezone.now().date()

    # Get min date from EnergyRecord to determine available weeks
    min_date_qs = EnergyRecord.objects.filter(
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(min_date=Min('date'))
    min_date = min_date_qs['min_date']
    if not min_date:
        # No data, handle gracefully
        context = {
            'week_options': [],
            'previous_week_name': 'N/A',
            'last_week_co2': '0.0',
            'current_week_so_far_co2': '0.0',
            'predicted_week_co2': '0.0',
            'change_percent': '0.00%',
            'change_direction': '▼',
            'change_class': 'green-arrow',
            'chart_labels': json.dumps([]),
            'prev_week_data': json.dumps([]),
            'current_week_data': json.dumps([]),
            'threshold': 180,
        }
        return render(request, 'users/userEmmision.html', context)

    # Generate week options: Weeks from min_date to now, labeled as Week 1, Week 2, etc.
    week_options = []
    current_week_start = min_date - timedelta(days=min_date.weekday())  # Monday of min_date week
    week_num = 1
    while current_week_start <= now:
        week_end = current_week_start + timedelta(days=6)
        week_options.append({
            'value': week_num,
            'label': f'Week {week_num}',
            'start_date': current_week_start,
            'end_date': week_end,
        })
        current_week_start += timedelta(days=7)
        week_num += 1

    # Reverse to have latest first, but keep numbering ascending
    week_options.reverse()

    # Get selected week from GET, default to latest (Week with highest num)
    selected_week_num = request.GET.get('week')
    if selected_week_num:
        try:
            selected_week_num = int(selected_week_num)
        except ValueError:
            selected_week_num = len(week_options)
    else:
        selected_week_num = len(week_options)  # Latest

    # Find selected week
    selected_week = next((w for w in week_options if w['value'] == selected_week_num), week_options[-1] if week_options else None)
    if not selected_week:
        selected_week = week_options[0] if week_options else None

    week_start = selected_week['start_date']
    week_end = selected_week['end_date']

    # Previous week
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_end - timedelta(days=7)
    previous_week_name = f"Week {selected_week_num - 1}" if selected_week_num > 1 else "Previous Week"

    # Last week total CO2
    last_week_total_co2 = EnergyRecord.objects.filter(
        date__gte=prev_week_start,
        date__lte=prev_week_end,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # Current week so far CO2 (up to today if within week)
    current_week_end = min(week_end, now)
    current_week_so_far_co2 = EnergyRecord.objects.filter(
        date__gte=week_start,
        date__lte=current_week_end,
        device__office__office_id__in=valid_office_ids
    ).exclude(
        device__office__name='DS'
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # Days so far in week
    days_so_far = (current_week_end - week_start).days + 1

    # Predicted this week CO2
    avg_daily_co2 = current_week_so_far_co2 / days_so_far if days_so_far > 0 else 0
    predicted_week_co2 = avg_daily_co2 * 7

    # Change in emissions
    if last_week_total_co2 > 0:
        change_percent = ((current_week_so_far_co2 - last_week_total_co2) / last_week_total_co2) * 100
    else:
        change_percent = 0
    change_direction = '▲' if change_percent > 0 else '▼'
    change_class = 'red-arrow' if change_percent > 0 else 'green-arrow'

    # Chart data: Daily CO2 for selected week
    daily_data = EnergyRecord.objects.filter(
        date__gte=week_start,
        date__lte=week_end,
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

    # Generate date range for 7 days
    date_range = []
    current = week_start
    while current <= week_end:
        date_range.append(current)
        current += timedelta(days=1)

    # Map data
    date_dict = {item['day_date']: item['total_co2'] or 0 for item in daily_data}

    # Current week data
    week_data = []
    labels = []
    for d in date_range:
        label = d.strftime('%a %d')  # e.g., Mon 01
        labels.append(label)
        week_data.append(date_dict.get(d, 0))

    threshold = 180  # Fixed

    context = {
        'office': request.user,
        'week_options': week_options,
        'selected_week': selected_week_num,
        'previous_week_name': previous_week_name,
        'last_week_co2': f"{last_week_total_co2:.1f}",
        'current_week_so_far_co2': f"{current_week_so_far_co2:.1f}",
        'predicted_week_co2': f"{predicted_week_co2:.0f}",
        'change_percent': f"{abs(change_percent):.2f}%",
        'change_direction': change_direction,
        'change_class': change_class,
        'chart_labels': json.dumps(labels),
        'week_data': json.dumps(week_data),
        'threshold': threshold,
    }
    return render(request, 'users/userEmmision.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def logout(request):
    auth.logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('users:index')
