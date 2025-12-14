@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def office_usage(request):
    from django.db.models import Sum, F, Max
    from django.db.models.functions import ExtractYear, ExtractMonth
    from django.utils import timezone
    from datetime import date, timedelta
    from datetime import datetime as dt
    import json

    office = request.user
    devices = office.devices.all()
    
    # Get unread notifications count
    unread_notifications_count = get_unread_notifications_count(office)
    
    # Get current rates
    cost_rate = CostSettings.get_current_rate().cost_per_kwh
    co2_rate = CO2Settings.get_current_rate().co2_emission_factor
    
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

    # Get current office data for selected filter
    office_record = SensorReading.objects.filter(
        device__in=devices,
        **filter_kwargs
    ).aggregate(
        total_energy=Sum('total_energy_kwh')
    )

    office_energy = office_record['total_energy'] or 0
    office_cost = office_energy * cost_rate
    office_co2 = office_energy * co2_rate

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
            total_energy=Sum('total_energy_kwh')
        ).order_by('date')
        
        date_dict = {record['date']: record['total_energy'] or 0 for record in week_data}
        chart_labels = []
        chart_dates = []
        chart_data = []
        current = week_start
        while current <= week_end:
            chart_labels.append(current.strftime('%a'))
            chart_dates.append(current.strftime('%A - %B %d, %Y'))
            chart_data.append(date_dict.get(current, 0))
            current += timedelta(days=1)
    elif selected_date:
        week_start = selected_date - timedelta(days=6)
        week_data = SensorReading.objects.filter(
            device__in=devices,
            date__gte=week_start,
            date__lte=selected_date
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('date')
        
        date_dict = {record['date']: record['total_energy'] or 0 for record in week_data}
        chart_labels = []
        chart_dates = []
        chart_data = []
        current = week_start
        while current <= selected_date:
            chart_labels.append(current.strftime('%a'))
            chart_dates.append(current.strftime('%A - %B %d, %Y'))
            chart_data.append(date_dict.get(current, 0))
            current += timedelta(days=1)
    else:
        # For month/year filters, get last 7 days with data
        week_data = SensorReading.objects.filter(
            device__in=devices,
            **filter_kwargs
        ).values('date').annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('-date')[:7]
        week_data = list(reversed(week_data))
        
        chart_labels = []
        chart_dates = []
        chart_data = []
        for record in week_data:
            chart_labels.append(record['date'].strftime('%a'))
            chart_dates.append(record['date'].strftime('%A - %B %d, %Y'))
            chart_data.append(record['total_energy'] or 0)

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
        'rank_change': f"{abs(rank_change):.1f}",
        'rank_change_direction': 'increase' if rank_change >= 0 else 'decrease',
        'comparison_label': comparison_label,
        'energy_status': energy_status,
        'status_class': status_class,
        'is_over_limit': is_over_limit,
        'chart_labels': json.dumps(chart_labels),
        'chart_dates': json.dumps(chart_dates),
        'chart_data': json.dumps(chart_data),
        'pie_chart_labels': json.dumps(pie_chart_labels),
        'pie_chart_data': json.dumps(pie_chart_data),
        'unread_notifications_count': unread_notifications_count,
    }
    return render(request, 'users/userUsage.html', context)