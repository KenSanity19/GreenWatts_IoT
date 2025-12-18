# GreenWatts IoT Energy Monitoring System - API Documentation

## Project Overview
GreenWatts is an IoT-based energy monitoring system that tracks real-time electricity consumption, calculates carbon emissions, and provides cost estimates for office environments using ESP32 microcontrollers with PZEM-004T energy meters.

---

## APIs Used in GreenWatts IoT Project

### 1. Gmail API (Google API)

**Type:** External API  
**Purpose:** Email communication for 2-Factor Authentication

**Description:**  
Google's official API for sending and managing emails programmatically.

**Implementation in Project:**
- Sends 2-Factor Authentication (2FA) OTP codes to users via email
- Used in `utils/gmail_api.py` with OAuth2 credentials
- Authenticates using refresh tokens stored in environment variables
- Sends security codes when users log in from new devices
- Provides secure email delivery without exposing SMTP credentials

**Key Configuration:**
```
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token
GMAIL_SENDER=your_email@gmail.com
```

**Key Files:**
- `utils/gmail_api.py`
- `get_gmail_token.py`

---

### 2. Supabase REST API

**Type:** External API  
**Purpose:** PostgreSQL database operations

**Description:**  
PostgreSQL database REST API provided by Supabase for database operations.

**Implementation in Project:**
- **ESP32 → Backend:** Sends sensor readings (voltage, current, energy data) from IoT devices
- **WiFi Configuration:** ESP32 fetches WiFi network credentials from admin panel
- Uses API key authentication for secure data transmission
- Stores data in tables: `tbl_sensor_reading`, `tbl_wifi_network`

**Endpoint:** `https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/`

**Key Files:**
- `esp32.ino` (supabaseUrl and wifiApiUrl variables)

---

### 3. Django REST Endpoints (Custom Backend APIs)

#### 3.1 Sensor Data API

**Endpoint:** `POST /api/sensor-data/`  
**Type:** Internal API  
**Purpose:** Receive IoT sensor data

**Description:**  
Custom REST API endpoint for receiving IoT sensor data from ESP32 devices.

**Functionality:**
- Receives daily batch readings from ESP32 devices (up to 8,640 readings/day)
- Accepts single or batch JSON payloads with voltage, current, timestamp
- Validates device existence in database
- Calculates energy consumption, carbon emissions, and costs
- Stores data in `SensorReading` and `EnergyRecord` tables

**Request Format (Batch):**
```json
{
  "device_id": 1,
  "reading_count": 8640,
  "readings": [
    {
      "voltage": 230.5,
      "current": 2.45,
      "timestamp": 1698345600
    }
  ]
}
```

**Response Format:**
```json
{
  "status": "success",
  "message": "Sensor data received successfully",
  "device_id": 1,
  "readings_stored": 8640
}
```

**Key File:** `greenwatts/sensors/views.py` - `receive_sensor_data()`

#### 3.2 WiFi Networks API

**Endpoint:** `GET /api/wifi-networks/`  
**Type:** Internal API  
**Purpose:** Dynamic WiFi configuration for ESP32

**Description:**  
Custom API for ESP32 to fetch WiFi credentials from admin settings.

**Functionality:**
- ESP32 requests available WiFi networks on startup
- Returns active networks ordered by priority
- Enables dynamic WiFi configuration without reprogramming ESP32
- Provides SSID, password, and priority for each network

**Response Format:**
```json
{
  "status": "success",
  "networks": [
    {
      "ssid": "office_wifi",
      "password": "password123",
      "priority": 1
    }
  ],
  "count": 1
}
```

**Key File:** `greenwatts/sensors/views.py` - `get_wifi_networks()`

#### 3.3 Admin Panel APIs

**Base Path:** `/adminpanel/`  
**Type:** Internal APIs  
**Purpose:** Admin dashboard operations

**Available Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/adminpanel/send-notification/` | POST | Send notifications to users |
| `/adminpanel/createOffice/` | POST | Create new office/user accounts |
| `/adminpanel/editOffice/<id>/` | POST | Update office details |
| `/adminpanel/createDevice/` | POST | Register new IoT devices |
| `/adminpanel/editDevice/<id>/` | POST | Update device settings |
| `/adminpanel/saveThresholds/` | POST | Configure energy thresholds |
| `/adminpanel/saveCostSettings/` | POST | Update cost per kWh |
| `/adminpanel/saveCO2Settings/` | POST | Update CO2 emission factors |
| `/adminpanel/get-days/` | GET | Fetch daily energy data |
| `/adminpanel/get_weeks/` | GET | Fetch weekly energy data |
| `/adminpanel/export-reports/` | GET | Export reports as CSV/PDF |
| `/adminpanel/createWifi/` | POST | Add WiFi network credentials |
| `/adminpanel/editWifi/<id>/` | POST | Update WiFi credentials |

**Key File:** `greenwatts/adminpanel/views.py`

#### 3.4 User Dashboard APIs

**Base Path:** `/` (users namespace)  
**Type:** Internal APIs  
**Purpose:** User dashboard and authentication

**Available Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/verify-otp/` | POST | Verify 2FA OTP codes |
| `/resend-otp/` | POST | Resend OTP to user email |
| `/notifications/` | GET | Fetch user notifications |
| `/get-user-days/` | GET | Fetch daily energy usage for user |
| `/get-user-weeks/` | GET | Fetch weekly energy usage for user |
| `/export-user-reports/` | GET | Export user reports |
| `/mark-notifications-read/` | POST | Mark notifications as read |
| `/logout/` | POST | User logout |

**Key File:** `greenwatts/users/views.py`

---

### 4. NTP (Network Time Protocol) API

**Type:** External API  
**Purpose:** Time synchronization

**Description:**  
Time synchronization protocol for accurate timestamps.

**Implementation in Project:**
- ESP32 syncs with `pool.ntp.org` on startup
- Ensures accurate timestamps for sensor readings
- Configured for UTC+8 (Philippines timezone)
- Critical for daily data aggregation at midnight

**Configuration:**
```cpp
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 28800; // UTC+8
const int daylightOffset_sec = 0;
```

**Key File:** `esp32.ino` - `syncTime()` function

---

### 5. Django Authentication API

**Type:** Internal API  
**Purpose:** User authentication and session management

**Description:**  
Django's built-in authentication system for secure user access.

**Implementation in Project:**
- User login/logout functionality
- Session management
- Password hashing and validation
- Custom user model (`Office` model as AUTH_USER_MODEL)
- Admin authentication for admin panel access

**Key Files:**
- `greenwatts/settings.py`
- `greenwatts/users/views.py`
- `greenwatts/adminpanel/views.py`

---

### 6. HTTP Client APIs (ESP32)

**Type:** Internal API  
**Purpose:** HTTP communication from ESP32

**Description:**  
ESP32's HTTPClient library for making HTTP requests to the Django backend.

**Implementation in Project:**
- Makes POST requests to send sensor data to Django backend
- Makes GET requests to fetch WiFi networks
- Implements retry logic for failed requests
- Queues failed requests in SPIFFS for later transmission
- Handles offline data storage and resending

**Key Features:**
- Automatic retry mechanism
- Offline data queuing
- Connection timeout handling
- SSL/TLS support

**Key File:** `esp32.ino` - Multiple functions using `HTTPClient`

---

## API Integration Flow

### Data Collection Flow
1. **ESP32** reads sensor data from PZEM-004T every 10 seconds
2. **ESP32** accumulates readings throughout the day
3. **ESP32** sends daily batch to **Django Backend** via **Sensor Data API**
4. **Django Backend** processes data and stores in **Supabase Database**
5. **Web Dashboard** displays data via **User/Admin APIs**

### Authentication Flow
1. User enters credentials on **Web Dashboard**
2. **Django Authentication API** validates credentials
3. If new device, **Gmail API** sends OTP via email
4. User enters OTP via **2FA Verification API**
5. System grants access to dashboard

### Configuration Flow
1. Admin configures WiFi networks via **Admin Panel APIs**
2. **ESP32** fetches networks via **WiFi Networks API**
3. **ESP32** connects using priority-based selection
4. **NTP API** synchronizes device time
5. Data collection begins

---

## Summary Table

| API | Type | Purpose | Used By | Authentication |
|-----|------|---------|---------|----------------|
| Gmail API | External | Send 2FA OTP emails | Django Backend | OAuth2 |
| Supabase REST API | External | Database operations | ESP32 | API Key |
| Sensor Data API | Internal | Receive IoT readings | ESP32 → Django | None |
| WiFi Networks API | Internal | Dynamic WiFi config | ESP32 | None |
| Admin Panel APIs | Internal | Admin operations | Web Dashboard | Session |
| User Dashboard APIs | Internal | User operations | Web Dashboard | Session + 2FA |
| NTP API | External | Time synchronization | ESP32 | None |
| Django Auth API | Internal | User authentication | Web Application | Session |
| HTTP Client API | Internal | ESP32 communication | ESP32 | None |

---

## Security Features

### API Security Measures
- **2-Factor Authentication** via Gmail API for user logins
- **Device fingerprinting** for trusted device management
- **API key authentication** for Supabase operations
- **Session-based authentication** for web dashboard
- **CSRF protection** for form submissions
- **SSL/TLS encryption** for all HTTP communications

### Data Protection
- **Environment variables** for sensitive credentials
- **Offline data queuing** prevents data loss during outages
- **Input validation** on all API endpoints
- **SQL injection protection** via Django ORM
- **Rate limiting** on authentication endpoints

---

## Technical Specifications

### Supported Data Formats
- **JSON** for API requests/responses
- **CSV/PDF** for report exports
- **Markdown** for documentation

### Database Tables
- `tbl_admin` - System administrators
- `tbl_office` - Office/user accounts  
- `tbl_device` - IoT devices
- `tbl_sensor_reading` - Raw sensor data
- `tbl_energy_record` - Daily energy summaries
- `tbl_threshold` - Energy efficiency thresholds
- `tbl_wifi_network` - WiFi network credentials

### Performance Metrics
- **10-second** sensor reading interval
- **Daily batch uploads** at midnight
- **Up to 8,640 readings** per device per day
- **30-day** trusted device memory
- **10-minute** OTP expiry time

---

*Document Version: 1.0*  
*Last Updated: January 2025*  
*Project: GreenWatts IoT Energy Monitoring System*