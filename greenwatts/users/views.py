from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required

def index(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = auth.authenticate(username=username, password=password)
        if user is not None:
            auth.login(request, user)
            messages.success(request, 'Login successful!')
            return redirect('users:dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
            return redirect('users:index')
    return render(request, 'index.html')

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
    if selected_date_str:
        try:
            # Parse mm/dd/yyyy format
            month, day, year = map(int, selected_date_str.split('/'))
            selected_date = date(year, month, day)
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    # Get devices for the user's office
    devices = office.devices.all()

    # Get unique dates for day options
    unique_dates_qs = EnergyRecord.objects.filter(device__in=devices).dates('date', 'day').distinct().order_by('-date')[:7]
    day_options = [d.strftime('%m/%d/%Y') for d in unique_dates_qs]

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

    # Active alerts: Devices with energy usage > 10 kWh (example threshold)
    alerts = EnergyRecord.objects.filter(
        device__in=devices,
        date=selected_date,
        total_energy_kwh__gt=10  # Threshold for alert
    ).select_related('device').values('device__office__name', 'total_energy_kwh')

    # Change in cost: Compare last week vs this week
    today = selected_date
    start_of_week = today - timedelta(days=today.weekday())  # Monday of current week
    end_of_week = start_of_week + timedelta(days=6)  # Sunday

    this_week_cost = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=start_of_week,
        date__lte=end_of_week
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    last_week_start = start_of_week - timedelta(days=7)
    last_week_end = end_of_week - timedelta(days=7)
    last_week_cost = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=last_week_start,
        date__lte=last_week_end
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    if last_week_cost > 0:
        cost_change_percent = ((this_week_cost - last_week_cost) / last_week_cost) * 100
    else:
        cost_change_percent = 0
    cost_change_direction = 'down' if cost_change_percent < 0 else 'up'
    cost_change_text = 'DECREASE' if cost_change_percent < 0 else 'INCREASE'

    # Calculate bar heights (normalize to 100% max)
    max_cost = max(this_week_cost, last_week_cost) if max(this_week_cost, last_week_cost) > 0 else 1
    last_week_height = (last_week_cost / max_cost) * 100
    this_week_height = (this_week_cost / max_cost) * 100

    # Carbon footprint: Till date and predicted
    current_year = today.year
    current_month = today.month
    days_so_far = today.day
    days_in_month = monthrange(current_year, current_month)[1]

    month_so_far_co2 = EnergyRecord.objects.filter(
        device__in=devices,
        date__year=current_year,
        date__month=current_month,
        date__lte=today
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    avg_daily_co2 = month_so_far_co2 / days_so_far if days_so_far > 0 else 0
    predicted_co2 = avg_daily_co2 * days_in_month

    # Calculate progress percentage for carbon footprint bar
    progress_percentage = (month_so_far_co2 / predicted_co2 * 100) if predicted_co2 > 0 else 0

    # Calculate bar heights for cost change (scale to 100%)
    max_cost = max(this_week_cost, last_week_cost) if this_week_cost or last_week_cost else 1
    last_week_height = (last_week_cost / max_cost) * 100 if max_cost > 0 else 0
    this_week_height = (this_week_cost / max_cost) * 100 if max_cost > 0 else 0

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
        'alerts': alerts,
        'this_week_cost': this_week_cost,
        'last_week_cost': last_week_cost,
        'last_week_height': last_week_height,
        'this_week_height': this_week_height,
        'cost_change_percent': f"{abs(cost_change_percent):.2f}",
        'cost_change_direction': cost_change_direction,
        'cost_change_text': cost_change_text,
        'month_so_far_co2': f"{month_so_far_co2:.2f}",
        'predicted_co2': f"{predicted_co2:.2f}",
        'progress_percentage': f"{progress_percentage:.1f}",
    }
    return render(request, 'users/dashboard.html', context)

@login_required
def office_usage(request):
    # Simple view to render the template, assuming data is handled elsewhere or dummy
    return render(request, 'users/userUsage.html')

@login_required
def user_reports(request):
    # Simple view to render the template, assuming data is handled elsewhere or dummy
    return render(request, 'users/userReports.html')

@login_required
def user_energy_cost(request):
    # Simple view to render the template, assuming data is handled elsewhere or dummy
    return render(request, 'users/userEnergyCost.html')

@login_required
def user_emmision(request):
    from django.db.models import Sum
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
        total_co2=Sum('carbon_emission_kgco2')
    )

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
    change_class = 'red-arrow' if change_percent > 0 else 'green-arrow'

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

    # Use up to 12 recent points
    labels = labels[-12:]
    prev_month_data = prev_month_data[-12:]
    current_month_data = current_month_data[-12:]

    threshold = 180  # Fixed

    context = {
        'previous_month_name': previous_month_name,
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
    }
    return render(request, 'users/userEmmision.html', context)

def logout(request):
    auth.logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('users:index')
