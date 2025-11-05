# TODO: Connect dashboard.html to Database

## Steps to Complete

- [x] Update dashboard view in greenwatts/users/views.py to fetch real data from EnergyRecord model for the logged-in user's office devices.
- [x] Calculate total energy usage, cost predicted, CO2 emissions for the selected date (or today if none).
- [x] Implement active alerts: Query devices with high energy usage (e.g., above a threshold) for the selected date.
- [x] Calculate change in cost: Compare total cost for last week vs this week.
- [x] Calculate carbon footprint: Total CO2 till date and predicted for the month.
- [x] Pass all calculated data as context to the dashboard.html template.
- [x] Update dashboard.html template to replace hardcoded values with context variables (e.g., {{ energy_usage }}, {{ cost_predicted }}, etc.).
- [x] Test the dashboard by running the server and checking if data loads dynamically.
