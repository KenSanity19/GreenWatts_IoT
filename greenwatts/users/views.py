from django.shortcuts import render, redirect
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control
from django.http import HttpResponse, JsonResponse
from ..adminpanel.models import Threshold
import csv

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def index(request):
    from ..adminpanel.login_attempts import is_locked_out, record_failed_attempt, clear_attempts, get_lockout_time_remaining
    
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
    from django.db.models.functions import ExtractYear, ExtractMonth
    from django.utils import timezone
    from datetime import timedelta, date
    from calendar import monthrange
    import json
    from ..sensors.models import EnergyRecord
    from datetime import datetime as dt

    office = request.user
    devices = office.devices.all()
    

    
    # Get selected day, month, year from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    
    # Force month filtering when month is selected
    if selected_month and not selected_day:
        if not selected_year:
            selected_year = str(dt.now().year)
    
    # Year options: all years with data for this office
    years_with_data = EnergyRecord.objects.filter(
        device__in=devices
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    year_options = [str(y) for y in years_with_data]
    
    # Month options: all months with data for this office
    months_with_data = EnergyRecord.objects.filter(
        device__in=devices
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')

    
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    month_options = [{'value': str(m), 'name': month_names[m-1]} for m in months_with_data]
    
    # Day options: all days with data, or filtered by month/year if selected
    if selected_month and selected_year:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__in=devices
        ).dates('date', 'day').order_by('-date')]
    else:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            device__in=devices
        ).dates('date', 'day').order_by('-date')]
    
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
        latest_data = EnergyRecord.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
        latest_date = latest_data['latest_date']
        if latest_date:
            filter_kwargs = {'date': latest_date}
            selected_date = latest_date
            selected_day = latest_date.strftime('%m/%d/%Y')
            selected_month = str(latest_date.month)
            selected_year = str(latest_date.year)
            level = 'day'

    # Total energy usage for selected filter
    energy_usage = EnergyRecord.objects.filter(
        device__in=devices,
        **filter_kwargs
    ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0

    # Cost predicted for selected filter
    cost_predicted = EnergyRecord.objects.filter(
        device__in=devices,
        **filter_kwargs
    ).aggregate(total=Sum('cost_estimate'))['total'] or 0

    # CO2 emissions for selected filter
    co2_emissions = EnergyRecord.objects.filter(
        device__in=devices,
        **filter_kwargs
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # Active alerts: Show overall computation as single entry
    threshold = Threshold.objects.first()
    if threshold:
        if energy_usage > threshold.energy_moderate_max:
            status = 'High'
        elif energy_usage > threshold.energy_efficient_max:
            status = 'Moderate'
        else:
            status = 'Efficient'
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
        
        current_cost = EnergyRecord.objects.filter(
            date__year=current_year, date__month=current_month,
            device__in=devices
        ).aggregate(total=Sum('cost_estimate'))['total'] or 0
        
        prev_cost = EnergyRecord.objects.filter(
            date__year=prev_year, date__month=prev_month,
            device__in=devices
        ).aggregate(total=Sum('cost_estimate'))['total'] or 0
        
        bar1_label = date(prev_year, prev_month, 1).strftime('%B %Y')
        bar2_label = date(current_year, current_month, 1).strftime('%B %Y')
    elif selected_date:
        # Compare selected_date and previous day
        previous_date = selected_date - timedelta(days=1)
        current_cost = EnergyRecord.objects.filter(
            date=selected_date, device__in=devices
        ).aggregate(total=Sum('cost_estimate'))['total'] or 0
        prev_cost = EnergyRecord.objects.filter(
            date=previous_date, device__in=devices
        ).aggregate(total=Sum('cost_estimate'))['total'] or 0
        
        bar1_label = previous_date.strftime('%B %d')
        bar2_label = selected_date.strftime('%B %d')
    else:
        # Default to last two days with data
        change_dates_qs = EnergyRecord.objects.filter(
            device__in=devices
        ).dates('date', 'day').distinct().order_by('-date')[:2]
        change_dates = list(change_dates_qs)
        if len(change_dates) >= 2:
            current_cost = EnergyRecord.objects.filter(
                date=change_dates[0], device__in=devices
            ).aggregate(total=Sum('cost_estimate'))['total'] or 0
            prev_cost = EnergyRecord.objects.filter(
                date=change_dates[1], device__in=devices
            ).aggregate(total=Sum('cost_estimate'))['total'] or 0
            
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
        days_with_data = EnergyRecord.objects.filter(
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
        'level': level,
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
    from django.db.models import Sum, F, Max
    from django.db.models.functions import ExtractYear, ExtractMonth
    from django.utils import timezone
    from datetime import date, timedelta
    from ..sensors.models import EnergyRecord
    from datetime import datetime as dt
    import json

    office = request.user
    devices = office.devices.all()
    
    # Get selected day, month, year from request
    selected_day = request.GET.get('selected_day')
    selected_month = request.GET.get('selected_month')
    selected_year = request.GET.get('selected_year')
    
    # Force month filtering when month is selected
    if selected_month and not selected_day:
        if not selected_year:
            selected_year = str(dt.now().year)
    
    # Year options: all years with data for this office
    years_with_data = EnergyRecord.objects.filter(
        device__in=devices
    ).annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    year_options = [str(y) for y in years_with_data]
    
    # Month options: all months with data for this office
    months_with_data = EnergyRecord.objects.filter(
        device__in=devices
    ).annotate(month=ExtractMonth('date')).values_list('month', flat=True).distinct().order_by('month')
    
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    month_options = [{'value': str(m), 'name': month_names[m-1]} for m in months_with_data]
    
    # Day options: all days with data, or filtered by month/year if selected
    if selected_month and selected_year:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            date__year=int(selected_year),
            date__month=int(selected_month),
            device__in=devices
        ).dates('date', 'day').order_by('-date')]
    else:
        day_options = [d.strftime('%m/%d/%Y') for d in EnergyRecord.objects.filter(
            device__in=devices
        ).dates('date', 'day').order_by('-date')]
    
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
        latest_data = EnergyRecord.objects.filter(device__in=devices).aggregate(latest_date=Max('date'))
        latest_date = latest_data['latest_date']
        if latest_date:
            filter_kwargs = {'date': latest_date}
            selected_date = latest_date
            selected_day = latest_date.strftime('%m/%d/%Y')
            selected_month = str(latest_date.month)
            selected_year = str(latest_date.year)
            level = 'day'

    # Get current office data for selected filter
    office_record = EnergyRecord.objects.filter(
        device__in=devices,
        **filter_kwargs
    ).aggregate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate'),
        total_co2=Sum('carbon_emission_kgco2')
    )

    office_energy = office_record['total_energy'] or 0
    office_cost = office_record['total_cost'] or 0
    office_co2 = office_record['total_co2'] or 0

    # Get all offices data for comparison
    all_offices_data = EnergyRecord.objects.filter(
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
    
    # Find office rank
    office_rank = 1
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
        
        pie_chart_labels.append(office_name)
        pie_chart_data.append(percentage)

    # Get week data for chart (last 7 days)
    if selected_date:
        week_start = selected_date - timedelta(days=6)
        week_data = EnergyRecord.objects.filter(
            device__in=devices,
            date__gte=week_start,
            date__lte=selected_date
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('date')
    else:
        # For month/year filters, get last 7 days with data
        week_data = EnergyRecord.objects.filter(
            device__in=devices,
            **filter_kwargs
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('-date')[:7]
        week_data = list(reversed(week_data))

    # Prepare chart data
    chart_labels = []
    chart_data = []
    
    if selected_date:
        date_dict = {record['date']: record['total_energy'] or 0 for record in week_data}
        current = week_start
        while current <= selected_date:
            chart_labels.append(current.strftime('%a'))
            chart_data.append(date_dict.get(current, 0))
            current += timedelta(days=1)
    else:
        # For month/year filters, use the data as is
        for record in week_data:
            chart_labels.append(record['date'].strftime('%a'))
            chart_data.append(record['total_energy'] or 0)

    # Calculate rank change vs previous period
    if selected_date:
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start - timedelta(days=1)
        prev_week_energy = EnergyRecord.objects.filter(
            device__in=devices,
            date__gte=prev_week_start,
            date__lte=prev_week_end
        ).aggregate(total=Sum('total_energy_kwh'))['total'] or 0
    else:
        # For month/year, compare with previous period
        prev_week_energy = office_energy * 0.9  # Placeholder calculation
    current_week_energy = sum(chart_data)
    if prev_week_energy > 0:
        rank_change = ((current_week_energy - prev_week_energy) / prev_week_energy) * 100
    else:
        rank_change = 0

    # Get threshold and determine status
    threshold = Threshold.objects.first()
    if threshold:
        if office_energy > threshold.energy_moderate_max:
            energy_status = 'High'
            status_class = 'status-high'
        elif office_energy > threshold.energy_efficient_max:
            energy_status = 'Moderate'
            status_class = 'status-moderate'
        else:
            energy_status = 'Efficient'
            status_class = 'status-efficient'
        
        is_over_limit = office_energy > threshold.energy_moderate_max
    else:
        energy_status = 'Unknown'
        status_class = 'status-unknown'
        is_over_limit = False

    # Format rank with proper suffix
    rank_suffix = 'th'
    if office_rank == 1:
        rank_suffix = 'st'
    elif office_rank == 2:
        rank_suffix = 'nd'
    elif office_rank == 3:
        rank_suffix = 'rd'
    
    formatted_rank = f"{office_rank}{rank_suffix}"
    
    context = {
        'office': office,
        'selected_date': selected_date,
        'day_options': day_options,
        'month_options': month_options,
        'year_options': year_options,
        'selected_day': selected_day,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'level': level,
        'office_energy_usage': f"{office_energy:.1f}",
        'office_cost_predicted': f"{office_cost:.2f}",
        'office_co2_emission': f"{office_co2:.1f}",
        'office_share_percentage': f"{office_share_percentage:.1f}",
        'office_rank': formatted_rank,
        'rank_change': f"{abs(rank_change):.1f}",
        'rank_change_direction': 'increase' if rank_change >= 0 else 'decrease',
        'energy_status': energy_status,
        'status_class': status_class,
        'is_over_limit': is_over_limit,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'pie_chart_labels': json.dumps(pie_chart_labels),
        'pie_chart_data': json.dumps(pie_chart_data),
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

    # CO2 emission for the week
    co2_emission = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=week_start,
        date__lte=week_end
    ).aggregate(total=Sum('carbon_emission_kgco2'))['total'] or 0

    # Office status based on energy usage
    threshold = Threshold.objects.first()
    if threshold:
        if total_energy_usage > threshold.energy_moderate_max:
            office_status = 'HIGH'
        elif total_energy_usage > threshold.energy_efficient_max:
            office_status = 'MODERATE'
        else:
            office_status = 'ACTIVE'
    else:
        office_status = 'ACTIVE'

    # Best performing day (lowest usage)
    if chart_values:
        min_energy = min(chart_values)
        min_index = chart_values.index(min_energy)
        best_performing_day = (week_start + timedelta(days=min_index)).strftime('%Y-%m-%d')
    else:
        best_performing_day = 'N/A'

    # Recommendation based on highest usage day
    if threshold and max_energy > threshold.energy_moderate_max:
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
        'co2_emission': f"{co2_emission:.2f}",
        'office_status': office_status,
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

    threshold = Threshold.objects.first()
    threshold_value = threshold.co2_moderate_max

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
        'threshold': threshold_value,
    }
    return render(request, 'users/userEmmision.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def export_user_reports(request):
    from django.db.models import Sum, Min
    from datetime import timedelta, date
    from ..sensors.models import EnergyRecord
    
    office = request.user
    devices = office.devices.all()
    
    selected_week_num = request.GET.get('week')
    if selected_week_num:
        try:
            selected_week_num = int(selected_week_num)
        except ValueError:
            selected_week_num = 1
    else:
        selected_week_num = 1
    
    # Get min date to calculate week range
    min_date_qs = EnergyRecord.objects.filter(device__in=devices).aggregate(min_date=Min('date'))
    min_date = min_date_qs['min_date']
    if not min_date:
        # No data case
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="user_report_no_data.csv"'
        writer = csv.writer(response)
        writer.writerow(['No data available'])
        return response
    
    # Calculate week start/end
    current_week_start = min_date - timedelta(days=min_date.weekday())
    week_start = current_week_start + timedelta(days=(selected_week_num - 1) * 7)
    week_end = week_start + timedelta(days=6)
    
    # Get week data
    week_data = EnergyRecord.objects.filter(
        device__in=devices,
        date__gte=week_start,
        date__lte=week_end
    ).values('date').annotate(
        total_energy=Sum('total_energy_kwh'),
        total_cost=Sum('cost_estimate'),
        total_co2=Sum('carbon_emission_kgco2')
    ).order_by('date')
    
    response = HttpResponse(content_type='text/csv')
    filename = f"user_report_week_{selected_week_num}_{office.username}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Energy Usage (kWh)', 'Cost Estimate (PHP)', 'CO2 Emission (kg)'])
    
    for record in week_data:
        writer.writerow([
            record['date'].strftime('%Y-%m-%d'),
            f"{record['total_energy']:.2f}" if record['total_energy'] else '0.00',
            f"{record['total_cost']:.2f}" if record['total_cost'] else '0.00',
            f"{record['total_co2']:.2f}" if record['total_co2'] else '0.00'
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
        
        from ..sensors.models import EnergyRecord
        days = EnergyRecord.objects.filter(
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

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def logout(request):
    auth.logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('users:index')
