/*
 * ESP32 PZEM-004T Energy Meter to Supabase (Daily Upload at 1:00 PM)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <PZEM004Tv30.h>
#include <time.h>
#include <SPIFFS.h>
#include <esp_task_wdt.h>

// ------------------ WiFi Settings ------------------
struct WiFiNetwork
{
  const char *ssid;
  const char *password;
};

// Hardcoded WiFi credentials
WiFiNetwork hardcodedNetworks[] = {
    {"greenwatts", "greenwatts123"},
    {"PLDTLANG", "Successed@123"},
    {"STUDENT-CONNECT", "IloveUSTP!"},
    {"SobaMask", "12345678"}};
const int numHardcodedNetworks = sizeof(hardcodedNetworks) / sizeof(hardcodedNetworks[0]);

// Dynamic WiFi from admin panel
String *dynamicSSIDs = nullptr;
String *dynamicPasswords = nullptr;
int numDynamicNetworks = 0;
bool usingDynamicNetworks = false;
const char *wifiApiUrl = "https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/tbl_wifi_network?is_active=eq.true&order=priority.asc";

// ------------------ Supabase Settings ------------------
const char *supabaseUrl = "https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/tbl_sensor_reading";
const char *supabaseApiKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNmd2V1eG9qZXdqd3h5em9teWFsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMjA0ODEsImV4cCI6MjA3NTU5NjQ4MX0.DiA1tj4Z66oLbiWo0fxGgKEFep-RE_wrybWp_LVwLT0";

// ------------------ Device Settings ------------------
const char *deviceId = "3";

// ------------------ PZEM Settings ------------------
#define PZEM_RX 16
#define PZEM_TX 17
#define PZEM_BAUD 9600
HardwareSerial pzemSerial(1);
PZEM004Tv30 pzem(pzemSerial, PZEM_RX, PZEM_TX);

const float voltageCalibrationFactor = 0.67;
const float currentCalibrationFactor = 1.1618;
const float voltageDisplayDivider = 1000.0; // Display voltage as decimal (e.g., 0.230 instead of 230)

// ------------------ Reading Interval ------------------
const unsigned long READ_INTERVAL = 10000; // 10 seconds
unsigned long lastReadTime = 0;
unsigned long lastValidReadTime = 0;

// ------------------ DAILY UPLOAD FLAG ------------------
bool uploadedToday = false;
String lastUploadDate = "";

// ------------------ Accumulators ------------------
float totalEnergy = 0; // kWh
float peakPower = 0;   // W
float totalCarbon = 0; // kg
float totalCost = 0;   // PHP

// ------------------ Power Outage Handling ------------------
bool deviceWasReset = true;
float storedEnergy = 0;
float storedCarbon = 0;
float storedCost = 0;
float storedPeakPower = 0;

// ------------------ NTP Settings ------------------
const char *ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 28800; // UTC+8
const int daylightOffset_sec = 0;

// =========================================================
// FUNCTION DECLARATIONS
// =========================================================
void checkMissedDailyUpload();
void sendToSupabase(float voltage, float current, float energy_kwh, float peak_power_w);
void testPLDTLANG();

// =========================================================
// TEST PLDTLANG CONNECTION
// =========================================================
void testPLDTLANG()
{
  Serial.println("\n=== Testing PLDTLANG Connection ===");
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  delay(1000);
  WiFi.mode(WIFI_STA);
  delay(1000);

  Serial.println("Attempting to connect to PLDTLANG...");
  WiFi.begin("PLDTLANG", "Successed@123");

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 60)
  {
    delay(500);
    Serial.print(".");
    if (attempts % 10 == 9)
    {
      Serial.println();
      Serial.print("Status: ");
      Serial.println(WiFi.status());
    }
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("\n✓ PLDTLANG Connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  }
  else
  {
    Serial.println("\n✗ PLDTLANG Failed!");
    Serial.print("Final Status: ");
    Serial.println(WiFi.status());
    Serial.println("\nPossible issues:");
    Serial.println("- Check if router is 2.4GHz (ESP32 doesn't support 5GHz)");
    Serial.println("- Verify password is correct");
    Serial.println("- Check signal strength (move ESP32 closer)");
    Serial.println("- Router might have MAC filtering enabled");
  }
  Serial.println("================================\n");
}

// =========================================================
// FETCH WIFI NETWORKS FROM ADMIN PANEL
// =========================================================
void fetchWiFiNetworks()
{
  if (WiFi.status() != WL_CONNECTED)
    return;

  HTTPClient http;
  http.begin(wifiApiUrl);
  http.addHeader("apikey", supabaseApiKey);
  http.addHeader("Authorization", String("Bearer ") + supabaseApiKey);
  http.setTimeout(5000);

  int httpCode = http.GET();

  if (httpCode == 200)
  {
    String payload = http.getString();

    int count = 0;
    int pos = 0;
    while ((pos = payload.indexOf("\"ssid\":", pos)) != -1)
    {
      count++;
      pos++;
    }

    if (count > 0)
    {
      if (dynamicSSIDs != nullptr)
      {
        delete[] dynamicSSIDs;
        delete[] dynamicPasswords;
      }

      dynamicSSIDs = new String[count];
      dynamicPasswords = new String[count];
      numDynamicNetworks = count;

      int networkIndex = 0;
      pos = 0;

      while (networkIndex < count && pos < payload.length())
      {
        int ssidStart = payload.indexOf("\"ssid\":\"", pos) + 8;
        int ssidEnd = payload.indexOf("\"", ssidStart);
        int passStart = payload.indexOf("\"password\":\"", ssidEnd) + 12;
        int passEnd = payload.indexOf("\"", passStart);

        if (ssidStart > 7 && ssidEnd > ssidStart && passStart > 11 && passEnd > passStart)
        {
          dynamicSSIDs[networkIndex] = payload.substring(ssidStart, ssidEnd);
          dynamicPasswords[networkIndex] = payload.substring(passStart, passEnd);
          networkIndex++;
        }

        pos = passEnd + 1;
      }

      Serial.println("Fetched " + String(numDynamicNetworks) + " WiFi networks from admin");
      usingDynamicNetworks = true;
    }
  }

  http.end();
}

// =========================================================
// WIFI AUTO-RECONNECT WITH FAILOVER
// =========================================================
void ensureWiFiConnected()
{
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("\n=== WiFi Connection Attempt ===");
    Serial.println("Scanning available networks...");

    int n = WiFi.scanNetworks();
    Serial.print("Found ");
    Serial.print(n);
    Serial.println(" networks:");
    for (int i = 0; i < n; i++)
    {
      Serial.print(i + 1);
      Serial.print(": ");
      Serial.print(WiFi.SSID(i));
      Serial.print(" (");
      Serial.print(WiFi.RSSI(i));
      Serial.println(" dBm)");
    }
    Serial.println();

    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(1000);
    WiFi.mode(WIFI_STA);
    delay(1000);

    // Try hardcoded networks first
    for (int i = 0; i < numHardcodedNetworks; i++)
    {
      Serial.print("Connecting to: ");
      Serial.println(hardcodedNetworks[i].ssid);
      Serial.print("Password: ");
      Serial.println(hardcodedNetworks[i].password);

      WiFi.begin(hardcodedNetworks[i].ssid, hardcodedNetworks[i].password);

      int retries = 0;
      while (WiFi.status() != WL_CONNECTED && retries < 40)
      {
        delay(500);
        Serial.print(".");
        if (retries % 10 == 9)
        {
          Serial.print(" Status: ");
          Serial.println(WiFi.status());
        }
        retries++;
      }

      if (WiFi.status() == WL_CONNECTED)
      {
        Serial.println("\n=== WiFi Connected ===");
        Serial.print("Network: ");
        Serial.println(hardcodedNetworks[i].ssid);
        Serial.print("IP Address: ");
        Serial.println(WiFi.localIP());
        Serial.print("Signal Strength: ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
        Serial.println("=====================");
        fetchWiFiNetworks();
        checkMissedDailyUpload();
        return;
      }
      Serial.println(" Failed!");
      Serial.print("WiFi Status Code: ");
      Serial.println(WiFi.status());
      WiFi.disconnect(true);
      delay(1000);
    }

    // Try dynamic networks from database
    if (usingDynamicNetworks && dynamicSSIDs != nullptr && numDynamicNetworks > 0)
    {
      for (int i = 0; i < numDynamicNetworks; i++)
      {
        Serial.print("Trying dynamic: ");
        Serial.println(dynamicSSIDs[i]);

        WiFi.begin(dynamicSSIDs[i].c_str(), dynamicPasswords[i].c_str());

        int dynamicRetries = 0;
        while (WiFi.status() != WL_CONNECTED && dynamicRetries < 20)
        {
          delay(500);
          Serial.print(".");
          dynamicRetries++;
        }

        if (WiFi.status() == WL_CONNECTED)
        {
          Serial.println("\n=== WiFi Connected ===");
          Serial.print("Network: ");
          Serial.println(dynamicSSIDs[i]);
          Serial.print("IP Address: ");
          Serial.println(WiFi.localIP());
          Serial.print("Signal Strength: ");
          Serial.print(WiFi.RSSI());
          Serial.println(" dBm");
          Serial.println("=====================");
          checkMissedDailyUpload();
          return;
        }
        Serial.println(" Failed!");
        WiFi.disconnect(true);
        delay(2000);
      }
    }

    // Final fallback - try hardcoded networks again
    for (int i = 0; i < numHardcodedNetworks; i++)
    {
      Serial.print("Trying fallback: ");
      Serial.println(hardcodedNetworks[i].ssid);
      WiFi.begin(hardcodedNetworks[i].ssid, hardcodedNetworks[i].password);

      int fallbackRetries = 0;
      while (WiFi.status() != WL_CONNECTED && fallbackRetries < 20)
      {
        delay(500);
        Serial.print(".");
        fallbackRetries++;
      }

      if (WiFi.status() == WL_CONNECTED)
      {
        Serial.println("\n=== WiFi Connected ===");
        Serial.print("Network: ");
        Serial.println(hardcodedNetworks[i].ssid);
        Serial.print("IP Address: ");
        Serial.println(WiFi.localIP());
        Serial.print("Signal Strength: ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
        Serial.println("=====================");
        fetchWiFiNetworks();
        checkMissedDailyUpload();
        return;
      }
      Serial.println(" Failed!");
      WiFi.disconnect(true);
      delay(2000);
    }
    Serial.println("All networks failed!");
  }
}

// =========================================================
// CHECK MISSED DAILY UPLOAD
// =========================================================
void checkMissedDailyUpload()
{
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo))
    return;

  char currentDate[11];
  strftime(currentDate, sizeof(currentDate), "%Y-%m-%d", &timeinfo);

  // If we have accumulated data and it's a new day, send it
  if (totalEnergy > 0 && lastUploadDate != String(currentDate))
  {
    Serial.println("\n--- Sending Missed Daily Summary ---");
    sendToSupabase(230.0, 2.0, totalEnergy, peakPower);

    // Reset accumulators
    totalEnergy = 0;
    peakPower = 0;
    totalCarbon = 0;
    totalCost = 0;

    // Clear stored data
    SPIFFS.remove("/accumulated.txt");

    // Update last upload date
    lastUploadDate = String(currentDate);
    uploadedToday = true;
  }
}

// =========================================================
// UPLOAD YESTERDAY'S DATA NOW
// =========================================================
void uploadNowAndReset()
{
  if (totalEnergy > 0 && WiFi.status() == WL_CONNECTED)
  {
    Serial.println("\n--- Manual Upload: Sending yesterday's data ---");

    struct tm timeinfo;
    time_t now = time(nullptr);
    now -= 24 * 60 * 60; // Yesterday
    localtime_r(&now, &timeinfo);

    char buf[25];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);

    String payload = "{";
    payload += "\"date\":\"" + String(buf) + "\",";
    payload += "\"voltage\":253.4,";
    payload += "\"current\":0.0,";
    payload += "\"total_energy_kwh\":" + String(totalEnergy, 4) + ",";
    payload += "\"peak_power_w\":" + String(peakPower, 2) + ",";
    payload += "\"device_id\":" + String(deviceId);
    payload += "}";

    Serial.println("Payload: " + payload);

    HTTPClient http;
    http.begin(supabaseUrl);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("apikey", supabaseApiKey);
    http.addHeader("Authorization", String("Bearer ") + supabaseApiKey);

    int httpCode = http.POST(payload);
    Serial.print("HTTP Response: ");
    Serial.println(httpCode);

    if (httpCode == 201)
    {
      Serial.println("SUCCESS: Yesterday's data uploaded!");

      // Reset accumulators
      totalEnergy = 0;
      peakPower = 0;
      totalCarbon = 0;
      totalCost = 0;

      // Clear stored data
      SPIFFS.remove("/accumulated.txt");

      // Update upload date to today
      struct tm currentTime;
      if (getLocalTime(&currentTime))
      {
        char currentDate[11];
        strftime(currentDate, sizeof(currentDate), "%Y-%m-%d", &currentTime);
        lastUploadDate = String(currentDate);
        uploadedToday = true;
      }

      Serial.println("Accumulators reset for today");
    }
    else
    {
      Serial.println("FAILED: Could not upload data");
    }

    http.end();
  }
  else if (totalEnergy <= 0)
  {
    Serial.println("No data to upload");
  }
  else
  {
    Serial.println("WiFi not connected");
  }
}

// =========================================================
// NTP TIME SYNC
// =========================================================
void syncTime()
{
  Serial.println("Synchronizing time with NTP...");
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  struct tm timeinfo;
  int attempts = 0;
  while (!getLocalTime(&timeinfo) && attempts < 20)
  {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println("\nTime synchronized.");
}

// =========================================================
// SAVE/LOAD ACCUMULATED DATA (SPIFFS)
// =========================================================
void saveAccumulatedData()
{
  File f = SPIFFS.open("/accumulated.txt", FILE_WRITE);
  if (!f)
    return;
  f.println(String(totalEnergy, 6));
  f.println(String(peakPower, 2));
  f.println(String(totalCarbon, 6));
  f.println(String(totalCost, 2));
  f.close();
}

void loadAccumulatedData()
{
  if (!SPIFFS.exists("/accumulated.txt"))
    return;
  File f = SPIFFS.open("/accumulated.txt", FILE_READ);
  if (!f)
    return;
  if (f.available())
    totalEnergy = f.readStringUntil('\n').toFloat();
  if (f.available())
    peakPower = f.readStringUntil('\n').toFloat();
  if (f.available())
    totalCarbon = f.readStringUntil('\n').toFloat();
  if (f.available())
    totalCost = f.readStringUntil('\n').toFloat();
  f.close();
  Serial.println("Restored accumulated data from storage.");
}

// =========================================================
// SAVE FAILED PAYLOAD (SPIFFS)
// =========================================================
void saveToQueue(String payload)
{
  File f = SPIFFS.open("/queue.txt", FILE_APPEND);
  if (!f)
  {
    Serial.println("ERROR: Failed to open queue file!");
    return;
  }
  f.println(payload);
  f.close();
  Serial.println("Saved unsent data to queue.");
}

// =========================================================
// HANDLE WIFI DISCONNECTION AT MIDNIGHT
// =========================================================
void handleMidnightDisconnection()
{
  if (WiFi.status() != WL_CONNECTED && totalEnergy > 0)
  {
    Serial.println("WiFi disconnected - queuing current day's data");

    // Create payload for current day's accumulated data
    struct tm timeinfo;
    time_t now = time(nullptr);
    now -= 24 * 60 * 60; // Yesterday's date
    localtime_r(&now, &timeinfo);

    char buf[25];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);

    String payload = "{";
    payload += "\"date\":\"" + String(buf) + "\",";
    payload += "\"voltage\":230.0,";
    payload += "\"current\":2.0,";
    payload += "\"total_energy_kwh\":" + String(totalEnergy, 3) + ",";
    payload += "\"peak_power_w\":" + String(peakPower, 2) + ",";
    payload += "\"device_id\":" + String(deviceId);
    payload += "}";

    saveToQueue(payload);
  }

  // Reset accumulators for new day
  totalEnergy = 0;
  peakPower = 0;
  totalCarbon = 0;
  totalCost = 0;
  SPIFFS.remove("/accumulated.txt");
}

// =========================================================
// RESEND QUEUE
// =========================================================
void resendQueue()
{
  if (!SPIFFS.exists("/queue.txt") || WiFi.status() != WL_CONNECTED)
    return;

  File f = SPIFFS.open("/queue.txt", FILE_READ);
  if (!f)
    return;

  Serial.println("\nTrying to resend queued data...");
  String allLines = "";
  String tempLines = "";

  HTTPClient http;
  http.begin(supabaseUrl);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", supabaseApiKey);
  http.addHeader("Authorization", String("Bearer ") + supabaseApiKey);
  http.setTimeout(5000); // Shorter timeout to prevent blocking

  while (f.available())
  {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() < 5)
      continue;

    allLines += line + "\n";

    Serial.print("Re-sending: ");
    Serial.println(line);

    int code = http.POST(line);

    if (code == 201)
    {
      Serial.println("Re-uploaded successfully!");
    }
    else
    {
      Serial.print("Failed again: ");
      Serial.println(code);
      tempLines += line + "\n";
    }
    delay(100);
  }

  f.close();
  http.end();

  // Rewrite queue with only failed items
  SPIFFS.remove("/queue.txt");
  if (tempLines.length() > 0)
  {
    File newF = SPIFFS.open("/queue.txt", FILE_WRITE);
    if (newF)
    {
      newF.print(tempLines);
      newF.close();
    }
  }
  else
  {
    Serial.println("All queued data sent successfully!");
  }
}

// =========================================================
// SEND TO SUPABASE
// =========================================================
void sendToSupabase(float voltage, float current, float energy_kwh, float peak_power_w)
{

  struct tm timeinfo;
  time_t now = time(nullptr);

  // Use yesterday's date
  now -= 24 * 60 * 60;
  localtime_r(&now, &timeinfo);

  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);

  String payload = "{";
  payload += "\"date\":\"" + String(buf) + "\",";
  payload += "\"voltage\":" + String(voltage, 2) + ",";
  payload += "\"current\":" + String(current, 3) + ",";
  payload += "\"total_energy_kwh\":" + String(energy_kwh, 3) + ",";
  payload += "\"peak_power_w\":" + String(peak_power_w, 2) + ",";
  payload += "\"device_id\":" + String(deviceId);
  payload += "}";

  Serial.println("\n=== JSON Payload ===");
  Serial.println(payload);

  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("WiFi offline — saving to queue.");
    saveToQueue(payload);
    return;
  }

  HTTPClient http;
  http.begin(supabaseUrl);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", supabaseApiKey);
  http.addHeader("Authorization", String("Bearer ") + supabaseApiKey);

  int httpCode = http.POST(payload);
  Serial.print("Supabase HTTP Response: ");
  Serial.println(httpCode);

  if (httpCode != 201)
  {
    saveToQueue(payload);
  }
  else
  {
    Serial.println("Upload success!");
  }

  http.end();
}

// =========================================================
// SETUP
// =========================================================
void setup()
{
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n\n=== GreenWatts ESP32 Starting ===");

  if (!SPIFFS.begin(true))
    Serial.println("SPIFFS Mount Failed!");

  pzemSerial.begin(PZEM_BAUD, SERIAL_8N1, PZEM_RX, PZEM_TX);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);
  delay(1000);

  // Test PLDTLANG connection first
  testPLDTLANG();

  ensureWiFiConnected();

  syncTime();

  // Fetch WiFi networks from admin panel
  fetchWiFiNetworks();

  // Load accumulated data if device was reset (for blackout protection)
  loadAccumulatedData();
  deviceWasReset = false;

  // Call this manually to upload yesterday's data
  uploadNowAndReset();

  resendQueue();
}

// =========================================================
// LOOP
// =========================================================
void loop()
{
  ensureWiFiConnected();

  unsigned long currentMillis = millis();

  // Read PZEM every 10 seconds
  if (currentMillis - lastReadTime >= READ_INTERVAL)
  {
    float voltage = pzem.voltage();
    float current = pzem.current();
    float power = pzem.power();

    // Apply calibration
    voltage = voltage * voltageCalibrationFactor;
    current = current * currentCalibrationFactor;
    power = voltage * current;

    // Only process valid readings
    if (!isnan(voltage) && !isnan(current) && !isnan(power) && voltage > 0)
    {
      // Calculate energy for this reading interval (10 seconds)
      float deltaEnergy = power * 10.0 / 3600000.0; // W * 10_seconds / (3600_s/h * 1000_W/kW) = kWh

      if (deltaEnergy > 0 && deltaEnergy < 10) // Reasonable bounds check
      {
        totalEnergy += deltaEnergy;
        totalCarbon += deltaEnergy * 0.475; // Philippines grid factor
        totalCost += deltaEnergy * 12.0;    // PHP per kWh
      }

      if (power > peakPower)
        peakPower = power;

      lastValidReadTime = currentMillis;

      // Save accumulated data every 10 readings (10 minutes)
      static int readingCount = 0;
      if (++readingCount >= 10)
      {
        saveAccumulatedData();
        readingCount = 0;
      }

      // ------------------ DEBUG PRINT ------------------
      struct tm timeinfo;
      if (getLocalTime(&timeinfo))
      {
        char timeStr[20];
        strftime(timeStr, sizeof(timeStr), "%H:%M:%S", &timeinfo);
        Serial.println("\n=== ENERGY READING ===");
        Serial.print("Time: ");
        Serial.println(timeStr);
        Serial.print("Voltage: ");
        Serial.print(voltage / voltageDisplayDivider, 3);
        Serial.println(" V");
        Serial.print("Current: ");
        Serial.print(current, 3);
        Serial.println(" A");
        Serial.print("Power: ");
        Serial.print(power, 2);
        Serial.println(" W");
        Serial.print("Total Energy: ");
        Serial.print(totalEnergy, 4);
        Serial.println(" kWh");
        Serial.print("Peak Power: ");
        Serial.print(peakPower, 2);
        Serial.println(" W");
        Serial.println("=====================");
      }
    }
    else
    {
      Serial.println("Invalid PZEM reading - skipping");
    }

    lastReadTime = currentMillis;
  }

  // Daily upload at exactly 12:00 AM (00:00)
  struct tm timeinfo;
  if (getLocalTime(&timeinfo))
  {
    if (timeinfo.tm_hour == 0 && timeinfo.tm_min == 0)
    {
      if (!uploadedToday)
      {
        Serial.println("\n--- Midnight Reset ---");

        if (WiFi.status() == WL_CONNECTED && totalEnergy > 0)
        {
          Serial.println("Sending Daily Summary");
          sendToSupabase(230.0, 2.0, totalEnergy, peakPower);
        }
        else
        {
          handleMidnightDisconnection();
        }

        // Update last upload date
        char currentDate[11];
        strftime(currentDate, sizeof(currentDate), "%Y-%m-%d", &timeinfo);
        lastUploadDate = String(currentDate);
        uploadedToday = true;
      }
    }
    else
    {
      uploadedToday = false;
    }
  }

  // Try to resend queue if WiFi is connected
  static unsigned long lastQueueCheck = 0;
  if (WiFi.status() == WL_CONNECTED && (currentMillis - lastQueueCheck > 30000))
  {
    resendQueue();
    lastQueueCheck = currentMillis;
  }

  delay(1000);
}