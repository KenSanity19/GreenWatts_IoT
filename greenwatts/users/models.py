from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from greenwatts.adminpanel.models import Admin

class OfficeManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, email, password, **extra_fields)

class Office(AbstractBaseUser, PermissionsMixin):
    office_id = models.AutoField(primary_key=True)  # PK
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)

    # Login credentials
    username = models.CharField(max_length=150, unique=True)
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
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = OfficeManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = "tbl_office"

    def __str__(self):
        return f"{self.name} ({self.location})"
