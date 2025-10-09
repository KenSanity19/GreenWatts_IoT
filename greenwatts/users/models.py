from django.db import models
from django.contrib.auth.hashers import make_password
from greenwatts.adminpanel.models import Admin

class Office(models.Model):
    office_id = models.AutoField(primary_key=True)  # PK
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)

    # Login credentials
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=255)  # Will store hashed password
    email = models.EmailField(unique=True)

    # Department can be "office", "viewer", etc.
    department = models.CharField(max_length=50, default="office")

    # Foreign Key to admin
    admin = models.ForeignKey(
        "adminpanel.Admin",  # this should match your tbl_admin model name
        on_delete=models.CASCADE,
        related_name="offices"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_office"

    def save(self, *args, **kwargs):
        # Ensure password is hashed before saving
        if not self.password.startswith("pbkdf2_"):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.location})"
