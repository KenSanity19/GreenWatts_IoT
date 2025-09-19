from django.db import models

class Admin(models.Model):
    admin_id = models.AutoField(primary_key=True)  # Primary Key
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)  # store hashed passwords, not plain text
    role = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)  # auto timestamp when created

    class Meta:
        db_table = "tbl_admin"  # custom table name

    def __str__(self):
        return self.username
