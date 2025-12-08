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

class Threshold(models.Model):
    threshold_id = models.AutoField(primary_key=True)
    energy_efficient_max = models.FloatField(default=10.0)  # Max for Efficient (e.g., <=10)
    energy_moderate_max = models.FloatField(default=20.0)   # Max for Moderate (e.g., >10 and <=20)
    energy_high_max = models.FloatField(default=30.0)       # Max for High (e.g., >20 and <=30)
    co2_efficient_max = models.FloatField(default=8.0)      # Max for Efficient CO2
    co2_moderate_max = models.FloatField(default=13.0)      # Max for Moderate CO2
    co2_high_max = models.FloatField(default=18.0)          # Max for High CO2
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_threshold"

    def __str__(self):
        return f"Thresholds: Energy Eff<{self.energy_efficient_max}, Mod<{self.energy_moderate_max}; CO2 Eff<{self.co2_efficient_max}, Mod<{self.co2_moderate_max}"

class ThresholdHistory(models.Model):
    history_id = models.AutoField(primary_key=True)
    energy_efficient_max = models.FloatField()
    energy_moderate_max = models.FloatField()
    energy_high_max = models.FloatField()
    co2_efficient_max = models.FloatField()
    co2_moderate_max = models.FloatField()
    co2_high_max = models.FloatField()
    created_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tbl_threshold_history"
        ordering = ['-created_at']

    def __str__(self):
        return f"Threshold History {self.history_id} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
