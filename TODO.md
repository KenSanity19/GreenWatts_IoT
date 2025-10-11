# TODO: Fix Password Hashing for Office Users

## Steps:

- [x] Edit adminpanel/views.py: Update create_office to use Office.objects.create_user() for proper hashing.
- [x] Edit adminpanel/views.py: Update edit_office to use set_password() when changing password.
- [ ] Hash existing plain text passwords using Django shell command.
- [ ] Test: Create a new office via the admin interface and verify password is hashed in DB.
- [ ] Verify login works with hashed passwords.
