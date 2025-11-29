# GreenWatts IoT Energy Monitoring System

## System Overview

GreenWatts is an IoT-based energy monitoring system that tracks real-time electricity consumption, calculates carbon emissions, and provides cost estimates for office environments. The system uses ESP32 microcontrollers with PZEM-004T energy meters to collect voltage and current data, which is then processed by a Django web application to provide comprehensive energy analytics.

### Key Features

- Real-time energy consumption monitoring
- Carbon footprint calculation
- Cost estimation and reporting
- Multi-office management
- Admin dashboard with threshold settings
- Offline data queuing for reliable data collection
- Daily energy summaries and reports

## System Architecture

```
ESP32 + PZEM-004T → WiFi → Django Backend → PostgreSQL Database
                                    ↓
                            Web Dashboard (Admin/User)
```

## Installation & Setup

### Prerequisites

- Python 3.8+
- PostgreSQL database
- ESP32 development board
- PZEM-004T energy meter

### Backend Setup

1. **Clone the repository**

```bash
git clone <repository-url>
cd GreenWatts_IoT
```

2. **Create virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Environment Configuration**
   Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://username:password@host:port/database
DEBUG=True
```

5. **Database Migration**

```bash
python manage.py makemigrations
python manage.py migrate
```

6. **Create Superuser**

```bash
python manage.py createsuperuser
```

7. **Run Development Server**

```bash
python manage.py runserver
```

### Hardware Setup

#### ESP32 + PZEM-004T Connections

```
PZEM-004T RX  → ESP32 GPIO 16 (RX2)
PZEM-004T TX  → ESP32 GPIO 17 (TX2)
PZEM-004T GND → ESP32 GND
PZEM-004T VCC → 5V Power Supply
```

#### ESP32 Configuration

1. Install required libraries in Arduino IDE:

   - WiFi
   - HTTPClient
   - PZEM004Tv30
   - SPIFFS

2. Update WiFi credentials in `esp32.ino`:

```cpp
const char *ssid = "YOUR_WIFI_SSID";
const char *password = "YOUR_WIFI_PASSWORD";
```

3. Configure device ID:

```cpp
const char *deviceId = "1";  // Unique device identifier
```

## API Documentation

### Base URL

```
http://localhost:8000/api/
```

### Authentication

The system uses Django's built-in authentication. Admin endpoints require admin login, while sensor data endpoints are publicly accessible for IoT devices.

### Endpoints

#### 1. Sensor Data Collection

**POST** `/api/sensor-data/`

Receives energy data from ESP32 devices.

**Request Headers:**

```
Content-Type: application/json
```

**Single Reading Format:**

```json
{
  "device_id": 1,
  "voltage": 230.5,
  "current": 2.45,
  "timestamp": 1698345600
}
```

**Batch Reading Format:**

```json
{
  "device_id": 1,
  "reading_count": 8640,
  "readings": [
    {
      "voltage": 230.5,
      "current": 2.45,
      "timestamp": 1698345600
    },
    {
      "voltage": 231.0,
      "current": 2.5,
      "timestamp": 1698345610
    }
  ]
}
```

**Response (Success):**

```json
{
  "status": "success",
  "message": "Sensor data received successfully",
  "device_id": 1,
  "readings_stored": 8640
}
```

**Response (Error):**

```json
{
  "status": "error",
  "message": "Device with ID 1 not found"
}
```

#### 2. Energy Records

The system automatically calculates and stores daily energy records with the following metrics:

- Total energy consumption (kWh)
- Peak power usage (W)
- Carbon emissions (kg CO2)
- Cost estimates (PHP)

### Data Models

#### Device

```python
{
    "device_id": 1,
    "installed_date": "2024-01-15",
    "status": "Active",
    "office_id": 1
}
```

#### SensorReading

```python
{
    "reading_id": 1,
    "device_id": 1,
    "voltage": 230.5,
    "current": 2.45,
    "timestamp": "2024-01-15T10:30:00Z",
    "created_at": "2024-01-15T10:30:05Z"
}
```

#### EnergyRecord

```python
{
    "record_id": 1,
    "device_id": 1,
    "date": "2024-01-15",
    "total_energy_kwh": 25.5,
    "peak_power_w": 1500.0,
    "carbon_emission_kgco2": 12.75,
    "cost_estimate": 318.75
}
```

## IoT Device Integration

### ESP32 Data Flow

1. **Data Collection**: PZEM-004T reads voltage/current every 10 seconds
2. **Data Accumulation**: ESP32 accumulates readings for daily summary
3. **Daily Transmission**: At midnight, sends accumulated data to Django backend
4. **Offline Queue**: Failed transmissions are queued in SPIFFS for retry
5. **Auto-Reconnect**: Automatic WiFi reconnection with retry mechanism

### Energy Calculations

```cpp
// Power calculation
float power = voltage * current;  // Watts

// Daily energy (kWh)
float energy_kwh = (total_power_sum * reading_interval) / (1000 * 3600);

// Carbon emissions (Philippines grid factor: 0.5 kg CO2/kWh)
float carbon_kg = energy_kwh * 0.5;

// Cost estimate (Philippines average: 12.50 PHP/kWh)
float cost_php = energy_kwh * 12.50;
```

### Offline Data Handling

The ESP32 implements a robust offline queuing system:

- Failed HTTP requests are saved to SPIFFS
- On WiFi reconnection, queued data is automatically retransmitted
- Ensures no data loss during network outages

## Web Dashboard Features

### User Dashboard

- Real-time energy consumption
- Daily/monthly usage reports
- Carbon footprint tracking
- Cost analysis

### Admin Panel

- Multi-office management
- Threshold configuration
- System-wide reports
- Device management

## Database Schema

### Core Tables

- `tbl_admin` - System administrators
- `tbl_office` - Office/user accounts
- `tbl_device` - IoT devices
- `tbl_sensor_reading` - Raw sensor data
- `tbl_energy_record` - Daily energy summaries
- `tbl_threshold` - Energy efficiency thresholds

## Development Guidelines

### Adding New Devices

1. Create device record in admin panel
2. Configure ESP32 with unique device_id
3. Deploy hardware at monitoring location
4. Verify data transmission in dashboard

### Extending API

- Follow Django REST conventions
- Add proper error handling
- Include request/response validation
- Update documentation

### Testing

```bash
# Run tests
python manage.py test

# Test specific app
python manage.py test greenwatts.sensors
```

## Deployment

### Production Settings

- Set `DEBUG = False`
- Configure proper `SECRET_KEY`
- Use production database
- Set up static file serving
- Configure HTTPS

### Environment Variables

```env
SECRET_KEY=production-secret-key
DATABASE_URL=postgresql://prod-db-url
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

## Troubleshooting

### Common Issues

**ESP32 not connecting to WiFi:**

- Check WiFi credentials
- Verify network connectivity
- Check power supply stability

**Data not appearing in dashboard:**

- Verify device_id exists in database
- Check API endpoint accessibility
- Review ESP32 serial output for errors

**Database connection errors:**

- Verify DATABASE_URL configuration
- Check PostgreSQL service status
- Ensure proper database permissions

### Monitoring

- Check ESP32 serial output for debugging
- Monitor Django logs for API errors
- Use database queries to verify data flow

## Future Enhancements

- Mobile application
- Real-time alerts and notifications
- Advanced analytics and ML predictions
- Integration with smart home systems
- Multi-tenant architecture
- API rate limiting and authentication

## Support

For technical support or questions:

- Check the troubleshooting section
- Review ESP32 serial output
- Examine Django server logs
- Contact development team

---

**Version:** 1.0  
**Last Updated:** January 2025  
**Developed by:** GreenWatts Development Team
