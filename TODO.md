# TODO: Fix Logout Functionality

## Tasks

- [x] Update logout links in user templates to point to 'users:logout' URL
  - [x] Update greenwatts/users/templates/users/dashboard.html
  - [x] Update greenwatts/users/templates/users/userReports.html
  - [x] Update greenwatts/users/templates/users/userEmmision.html
  - [x] Update greenwatts/users/templates/users/userEnergyCost.html
  - [x] Update greenwatts/users/templates/users/userUsage.html
- [x] Update logout links in admin templates to point to 'users:logout' URL
  - [x] Update greenwatts/adminpanel/templates/officeUsage.html
  - [x] Update greenwatts/adminpanel/templates/adminSetting.html
  - [x] Update greenwatts/adminpanel/templates/adminCosts.html
  - [x] Update greenwatts/adminpanel/templates/adminDashboard.html
  - [x] Update greenwatts/adminpanel/templates/adminReports.html
  - [x] Update greenwatts/adminpanel/templates/carbonEmission.html
- [ ] Add cache control decorator to the index view in greenwatts/users/views.py to prevent caching of the login page
