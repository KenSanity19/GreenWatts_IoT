# TODO: Fix Password Hashing for Office Users

## Steps:

- [x] Edit adminpanel/views.py: Update create_office to use Office.objects.create_user() for proper hashing.
- [x] Edit adminpanel/views.py: Update edit_office to use set_password() when changing password.
- [ ] Hash existing plain text passwords using Django shell command.
- [ ] Test: Create a new office via the admin interface and verify password is hashed in DB.
- [ ] Verify login works with hashed passwords.

# Add Recommendation Box Below Graph in Admin Reports

## Steps:

- [x] Edit greenwatts/adminpanel/static/adminCss/adminReports.css: Update .chart-recommendation styles to create a visible white box (background, padding, border, text color).
- [x] Edit greenwatts/adminpanel/templates/adminReports.html: (If needed) Enhance the recommendation div for better structure or add icon.
- [ ] Test: Run `python manage.py runserver` (if not active), then use browser to view http://localhost:8000/adminpanel/admin_reports/ and confirm the recommendation appears as a distinct box below the graph.
- [ ] Update progress in TODO.md after each step.
