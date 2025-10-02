from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from .models import Admin, Office
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
    return render(request, 'adminDashboard.html')

from .models import Admin, Office

def admin_setting(request):
    offices = Office.objects.all()
    return render(request, 'adminSetting.html', {'offices': offices})

def office_usage(request):
    return render(request, 'officeUsage.html')

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
