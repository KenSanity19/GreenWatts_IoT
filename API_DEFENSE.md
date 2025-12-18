# GreenWatts IoT Project - API Defense Documentation

## **APIs Used in GreenWatts IoT Project**

### **1. Gmail API (Google API)**
**What it is:** Google's official API for sending and managing emails programmatically.

**How it's used in our project:**
- Sends 2-Factor Authentication (2FA) OTP codes to users via email
- Used in `utils/gmail_api.py` with OAuth2 credentials
- Authenticates using refresh tokens stored in environment variables
- Sends security codes when users log in from new devices
- Provides secure email delivery without exposing SMTP credentials

**Key files:** `utils/gmail_api.py`, `get_gmail_token.py`

---

### **2. Supabase REST API**
**What it is:** PostgreSQL database REST API provided by Supabase for database operations.

**How it's used in our project:**
- **ESP32 → Backend:** Sends sensor readings (voltage, current, energy data) from IoT devices
- **WiFi Configuration:** ESP32 fetches WiFi network credentials from admin panel
- Endpoint: `https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/`
- Uses API key authentication for secure data transmission
- Stores data in tables: `tbl_sensor_reading`, `tbl_wifi_network`

**Key files:** `esp32.ino` (lines with `supabaseUrl` and `wifiApiUrl`)

---

### **3. Django REST Endpoints (Custom Backend APIs)**

#### **3.1 Sensor Data API**
**Endpoint:** `POST /api/sensor-data/`

**What it is:** Custom REST API endpoint for receiving IoT sensor data.

**How it's used:**
- Receives daily batch readings from ESP32 devices (up to 8,640 readings/day)
- Accepts single or batch JSON payloads with voltage, current, timestamp
- Validates device existence in database
- Calculates energy consumption, carbon emissions, and costs
- Stores data in `SensorReading` and `EnergyRecord` tables

**Key file:** `greenwatts/sensors/views.py` - `receive_sensor_data()`

---

#### **3.2 WiFi Networks API**
**Endpoint:** `GET /api/wifi-networks/`

**What it is:** Custom API for ESP32 to fetch WiFi credentials from admin settings.

**How it's used:**
- ESP32 requests available WiFi networks on startup
- Returns active networks ordered by priority
- Enables dynamic WiFi configuration without reprogramming ESP32
- Provides SSID, password, and priority for each network

**Key file:** `greenwatts/sensors/views.py` - `get_wifi_networks()`

---

#### **3.3 Admin Panel APIs**
**Endpoints:** Multiple endpoints under `/adminpanel/`

**What they are:** Backend APIs for admin dashboard operations.

**How they're used:**
- `POST /adminpanel/send-notification/` - Send notifications to users
- `POST /adminpanel/createOffice/` - Create new office/user accounts
- `POST /adminpanel/editOffice/<id>/` - Update office details
- `POST /adminpanel/createDevice/` - Register new IoT devices
- `POST /adminpanel/editDevice/<id>/` - Update device settings
- `POST /adminpanel/saveThresholds/` - Configure energy thresholds
- `POST /adminpanel/saveCostSettings/` - Update cost per kWh
- `POST /adminpanel/saveCO2Settings/` - Update CO2 emission factors
- `GET /adminpanel/get-days/` - Fetch daily energy data
- `GET /adminpanel/get_weeks/` - Fetch weekly energy data
- `GET /adminpanel/export-reports/` - Export reports as CSV/PDF
- `POST /adminpanel/createWifi/` - Add WiFi network credentials
- `POST /adminpanel/editWifi/<id>/` - Update WiFi credentials

**Key file:** `greenwatts/adminpanel/views.py`

---

#### **3.4 User Dashboard APIs**
**Endpoints:** Multiple endpoints under `/` (users namespace)

**What they are:** Backend APIs for user dashboard and authentication.

**How they're used:**
- `POST /verify-otp/` - Verify 2FA OTP codes
- `POST /resend-otp/` - Resend OTP to user email
- `GET /notifications/` - Fetch user notifications
- `GET /get-user-days/` - Fetch daily energy usage for user
- `GET /get-user-weeks/` - Fetch weekly energy usage for user
- `GET /export-user-reports/` - Export user reports
- `POST /mark-notifications-read/` - Mark notifications as read
- `POST /logout/` - User logout

**Key file:** `greenwatts/users/views.py`

---

### **4. NTP (Network Time Protocol) API**
**What it is:** Time synchronization protocol for accurate timestamps.

**How it's used in our project:**
- ESP32 syncs with `pool.ntp.org` on startup
- Ensures accurate timestamps for sensor readings
- Configured for UTC+8 (Philippines timezone)
- Critical for daily data aggregation at midnight

**Key file:** `esp32.ino` - `syncTime()` function

---

### **5. Django Authentication API**
**What it is:** Django's built-in authentication system.

**How it's used:**
- User login/logout functionality
- Session management
- Password hashing and validation
- Custom user model (`Office` model as AUTH_USER_MODEL)
- Admin authentication for admin panel access

**Key files:** `greenwatts/settings.py`, `greenwatts/users/views.py`, `greenwatts/adminpanel/views.py`

---

### **6. HTTP Client APIs (ESP32)**
**What it is:** ESP32's HTTPClient library for making HTTP requests.

**How it's used:**
- Makes POST requests to send sensor data to Django backend
- Makes GET requests to fetch WiFi networks
- Implements retry logic for failed requests
- Queues failed requests in SPIFFS for later transmission
- Handles offline data storage and resending

**Key file:** `esp32.ino` - Multiple functions using `HTTPClient`

---

## **Summary Table**

| API | Type | Purpose | Used By |
|-----|------|---------|---------|
| Gmail API | External | Send 2FA OTP emails | Django Backend |
| Supabase REST API | External | Database operations | ESP32 |
| Sensor Data API | Internal | Receive IoT readings | ESP32 → Django |
| WiFi Networks API | Internal | Dynamic WiFi config | ESP32 |
| Admin Panel APIs | Internal | Admin operations | Web Dashboard |
| User Dashboard APIs | Internal | User operations | Web Dashboard |
| NTP API | External | Time synchronization | ESP32 |
| Django Auth API | Internal | User authentication | Web Application |

---

All APIs work together to create a complete IoT energy monitoring system with secure authentication, real-time data collection, and comprehensive reporting capabilities.