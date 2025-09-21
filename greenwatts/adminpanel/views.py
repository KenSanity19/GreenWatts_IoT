from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Admin

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
                return redirect("adminpanel:admin_dashboard")  # your dashboard URL name
            else:
                messages.error(request, "Invalid password")
        except Admin.DoesNotExist:
            messages.error(request, "User does not exist")

    return render(request, "adminLogin.html")


def admin_dashboard(request):
    return render(request, 'adminDashboard.html')

def admin_setting(request):
    return render(request, 'adminSetting.html')

def office_usage(request):
    return render(request, 'officeUsage.html')
