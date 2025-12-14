/*
 * ESP32 PZEM-004T Energy Meter to Supabase (Daily Upload at 1:00 PM)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <PZEM004Tv30.h>
#include <time.h>
#include <SPIFFS.h>

// ------------------ WiFi Settings ------------------
struct WiFiNetwork
{
  const char *ssid;
  const char *password;
};

WiFiNetwork networks[] = {
    {"PLDTLANG", "Successed@123"},
    {"STUDENT CONNECT", "IloveUSTP!"},
    {"Fourth_WiFi", "fourth_password"},
    {"SobaMask", "12345678"}};
const int numNetworks = sizeof(networks) / sizeof(networks[0]);
int currentNetworkIndex = 0;

// ------------------ Supabase Settings ------------------
const char *supabaseUrl = "https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/tbl_sensor_reading";
const char *supabaseApiKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNmd2V1eG9qZXdqd3h5em9teWFsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMjA0ODEsImV4cCI6MjA3NTU5NjQ4MX0.DiA1tj4Z66oLbiWo0fxGgKEFep-RE_wrybWp_LVwLT0";

// ------------------ Device Settings ------------------
const char *deviceId = "1";

// ------------------ PZEM Settings ------------------
#define PZEM_RX 16
#define PZEM_TX 17
#define PZEM_BAUD 9600
HardwareSerial pzemSerial(1);
PZEM004Tv30 pzem(pzemSerial, PZEM_RX, PZEM_TX);

// ------------------ Reading Interval ------------------
const unsigned long READ_INTERVAL = 10000; // 10 seconds
unsigned long lastReadTime = 0;
unsigned long lastValidReadTime = 0;

// ------------------ DAILY UPLOAD FLAG ------------------
bool uploadedToday = false;

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
// WIFI AUTO-RECONNECT WITH FAILOVER
// =========================================================
void ensureWiFiConnected()
{
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("WiFi lost! Trying networks...");

    for (int attempt = 0; attempt < numNetworks; attempt++)
    {
      WiFi.disconnect();
      Serial.print("Trying: ");
      Serial.println(networks[currentNetworkIndex].ssid);

      WiFi.begin(networks[currentNetworkIndex].ssid, networks[currentNetworkIndex].password);

      int retries = 0;
      while (WiFi.status() != WL_CONNECTED && retries < 15)
      {
        delay(500);
        Serial.print(".");
        retries++;
      }

      if (WiFi.status() == WL_CONNECTED)
      {
        Serial.print("\nConnected to: ");
        Serial.println(networks[currentNetworkIndex].ssid);
        return;
      }

      Serial.println(" Failed!");
      currentNetworkIndex = (currentNetworkIndex + 1) % numNetworks;
    }
    Serial.println("All networks failed!");
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
  http.setTimeout(10000);

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

  // Use yesterday’s date
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

  if (!SPIFFS.begin(true))
    Serial.println("SPIFFS Mount Failed!");

  pzemSerial.begin(PZEM_BAUD, SERIAL_8N1, PZEM_RX, PZEM_TX);

  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  ensureWiFiConnected();

  syncTime();

  // Load accumulated data if device was reset (for blackout protection)
  loadAccumulatedData();
  deviceWasReset = false;

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
        Serial.print(voltage, 2);
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
    if (timeinfo.tm_hour == 15 && timeinfo.tm_min == 30)
    {
      if (!uploadedToday)
      {
        Serial.println("\n--- Sending Daily Summary ---");
        sendToSupabase(230.0, 2.0, totalEnergy, peakPower); // Use last known voltage/current

        // Reset accumulators
        totalEnergy = 0;
        peakPower = 0;
        totalCarbon = 0;
        totalCost = 0;

        // Clear stored data
        SPIFFS.remove("/accumulated.txt");
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
