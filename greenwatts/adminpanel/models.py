from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password

class Admin(models.Model):
    admin_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)  # store hashed passwords, not plain text
    name = models.CharField(max_length=150, null=True, blank=True)  # optional
    email = models.EmailField(unique=True, null=True, blank=True)   # optional
    role = models.CharField(max_length=50, default="superadmin")    # default role
    created_at = models.DateTimeField(default=timezone.now)         # auto timestamp

    class Meta:
        db_table = "tbl_admin"  # match your ERD / DB table

    def save(self, *args, **kwargs):
        # Ensure password is hashed before saving
        if not self.password.startswith("pbkdf2_"):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

class EnergyThreshold(models.Model):
    threshold_id = models.AutoField(primary_key=True)
    efficient_max = models.FloatField(default=10.0)
    moderate_max = models.FloatField(default=20.0)
    high_max = models.FloatField(default=30.0)
    created_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tbl_energy_threshold"
        ordering = ['-created_at']

    def __str__(self):
        return f"Energy Threshold {self.threshold_id}"

class CO2Threshold(models.Model):
    threshold_id = models.AutoField(primary_key=True)
    efficient_max = models.FloatField(default=8.0)
    moderate_max = models.FloatField(default=13.0)
    high_max = models.FloatField(default=18.0)
    created_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tbl_co2_threshold"
        ordering = ['-created_at']

    def __str__(self):
        return f"CO2 Threshold {self.threshold_id}"
