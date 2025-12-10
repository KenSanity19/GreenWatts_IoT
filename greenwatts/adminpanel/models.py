from django.db import models
from django.utils import timezone

class Admin(models.Model):
    admin_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)
    email = models.EmailField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    def __str__(self):
        return self.username

    class Meta:
        db_table = 'tbl_admin'



class EnergyThreshold(models.Model):
    threshold_id = models.AutoField(primary_key=True)
    efficient_max = models.FloatField()
    moderate_max = models.FloatField()
    high_max = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tbl_energy_threshold'

class CO2Threshold(models.Model):
    threshold_id = models.AutoField(primary_key=True)
    efficient_max = models.FloatField()
    moderate_max = models.FloatField()
    high_max = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tbl_co2_threshold'

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('alert', 'Alert'),
    ]
    
    notification_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='info')
    target_office = models.ForeignKey('users.Office', on_delete=models.CASCADE, null=True, blank=True)
    is_global = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = 'tbl_notification'
        ordering = ['-created_at']