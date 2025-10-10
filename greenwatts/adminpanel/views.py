from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from .models import Admin
from greenwatts.users.models import Office
from ..sensors.models import Device
from ..sensors.models import EnergyRecord
from django.db.models import Sum, F
from datetime import datetime, timedelta
import json

def index(request):
    return HttpResponse("Hello from Admin app")

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


def admin_dashboard(request):
    from django.db.models import Max
    from django.db.models.functions import TruncDate
    from datetime import date
    from datetime import datetime as dt

    # Get unique dates from EnergyRecord, last 7 days with data, ordered descending
    unique_dates_qs = EnergyRecord.objects.dates('date', 'day').distinct().order_by('-date')[:7]
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
        latest_date_qs = EnergyRecord.objects.aggregate(latest_date=Max('date'))
        latest_date = latest_date_qs['latest_date']
        if latest_date:
            selected_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date

    # Aggregate sums for total energy usage, cost estimate, and carbon emission from selected date
    if selected_date:
        aggregates = EnergyRecord.objects.filter(date=selected_date).aggregate(
            total_energy_usage=Sum('total_energy_kwh'),
            total_cost_predicted=Sum('cost_estimate'),
            total_co2_emission=Sum('carbon_emission_kgco2')
        )
    else:
        aggregates = {
            'total_energy_usage': 0,
            'total_cost_predicted': 0,
            'total_co2_emission': 0
        }

    # Calculate predicted CO2 emission (simple projection: current emission * 10 as example)
    predicted_co2_emission = (aggregates['total_co2_emission'] or 0) * 10

    # Prepare dates for display
    if selected_date:
        current_date = selected_date.strftime("%B %d, %Y")
    else:
        current_date = datetime.now().strftime("%B %d, %Y")
    predicted_date = (dt.combine(selected_date, dt.min.time()) + timedelta(days=7)).strftime("%B %d, %Y") if selected_date else (datetime.now() + timedelta(days=7)).strftime("%B %d, %Y")

    # Aggregate energy usage per office from selected date
    from django.db.models import F
    # Get all valid office ids from Office table
    valid_office_ids = set(Office.objects.values_list('office_id', flat=True))

    if selected_date:
        office_energy_qs = EnergyRecord.objects.filter(
            date=selected_date,
            device__office__office_id__in=valid_office_ids
        ).exclude(
            device__office__name='DS'
        ).values(
            office_id=F('device__office__office_id'),
            office_name=F('device__office__name')
        ).annotate(
            total_energy=Sum('total_energy_kwh')
        ).order_by('-total_energy')
    else:
        office_energy_qs = []

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

    context = {
        'total_energy_usage': aggregates['total_energy_usage'] or 0,
        'total_cost_predicted': aggregates['total_cost_predicted'] or 0,
        'total_co2_emission': aggregates['total_co2_emission'] or 0,
        'predicted_co2_emission': predicted_co2_emission,
        'current_date': current_date,
        'predicted_date': predicted_date,
        'co2_emission_progress': co2_emission_progress,
        'active_alerts': active_alerts,
        'day_options': day_options,
        'selected_date': selected_date_str if selected_date_str else None,
    }
    return render(request, 'adminDashboard.html', context)

def admin_setting(request):
    offices = Office.objects.all()
    devices = Device.objects.select_related('office').all()
    return render(request, 'adminSetting.html', {'offices': offices, 'devices': devices})

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

def admin_reports(request):
    return render(request, 'adminReports.html')

def admin_costs(request):
    return render(request, 'adminCosts.html')

def carbon_emission(request):
    return render(request, 'carbonEmission.html')

@csrf_exempt
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

            office = Office(
                name=name,
                location=location,
                email=email,
                username=username,
                password=password,
                department=department,
                admin=admin
            )
            office.save()
            return JsonResponse({"status": "success", "message": "Office created successfully"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})

@csrf_exempt
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

@csrf_exempt
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
                office.password = new_password
            office.department = data.get("department", office.department)
            office.save()
            return JsonResponse({"status": "success", "message": "Office updated successfully"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})
