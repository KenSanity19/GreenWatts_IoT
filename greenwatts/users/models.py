from django.db import models
from greenwatts.adminpanel.models import Admin  # foreign key link to tbl_admin

class User(models.Model):
    user_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=128)
    role = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    # Foreign key to Admin
    admin = models.ForeignKey(Admin, on_delete=models.CASCADE)

    class Meta:
        db_table = "tbl_users"

    def __str__(self):
        return self.username
