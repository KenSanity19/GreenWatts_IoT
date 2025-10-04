from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from greenwatts.adminpanel.models import Office

def index(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        try:
            office = Office.objects.get(username=username)
            if check_password(password, office.password):
                request.session['office_id'] = office.office_id
                request.session['username'] = office.username
                messages.success(request, 'Login successful!')
                return redirect('users:dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
                return redirect('users:index')
        except Office.DoesNotExist:
            messages.error(request, 'Invalid username or password.')
            return redirect('users:index')
    return render(request, 'index.html')

def dashboard(request):
    if 'office_id' not in request.session:
        return redirect('users:index')
    office = Office.objects.get(office_id=request.session['office_id'])
    return render(request, 'users/dashboard.html', {'office': office})

def logout(request):
    request.session.flush()
    messages.info(request, 'You have been logged out.')
    return redirect('users:index')
