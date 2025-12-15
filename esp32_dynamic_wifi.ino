/*
 * ESP32 PZEM-004T Energy Meter with Dynamic WiFi Management
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <PZEM004Tv30.h>
#include <time.h>
#include <SPIFFS.h>
#include <esp_task_wdt.h>
#include <ArduinoJson.h>

// ------------------ WiFi Settings ------------------
struct WiFiNetwork
{
  String ssid;
  String password;
  int priority;
};

// Hardcoded fallback networks
WiFiNetwork fallbackNetworks[] = {
    {"greenwatts", "greenwatts123", 99},
    {"PLDTLANG", "Successed@123", 99},
    {"STUDENT-CONNECT", "IloveUSTP!", 99},
    {"SobaMask", "12345678", 99}};
const int numFallbackNetworks = sizeof(fallbackNetworks) / sizeof(fallbackNetworks[0]);

// Dynamic networks from admin panel
WiFiNetwork* dynamicNetworks = nullptr;
int numDynamicNetworks = 0;
int currentNetworkIndex = 0;
bool usingDynamicNetworks = false;

// ------------------ API Settings ------------------
const char *supabaseUrl = "https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/tbl_sensor_reading";
const char *supabaseApiKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNmd2V1eG9qZXdqd3h5em9teWFsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMjA0ODEsImV4cCI6MjA3NTU5NjQ4MX0.DiA1tj4Z66oLbiWo0fxGgKEFep-RE_wrybWp_LVwLT0";
const char *wifiApiUrl = "http://192.168.1.100:8000/api/wifi-networks/";  // Update with your server IP

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
// FETCH WIFI NETWORKS FROM ADMIN PANEL
// =========================================================
void fetchWiFiNetworks()
{
  if (WiFi.status() != WL_CONNECTED) return;
  
  HTTPClient http;
  http.begin(wifiApiUrl);
  http.setTimeout(5000);
  
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String payload = http.getString();
    
    DynamicJsonDocument doc(2048);
    deserializeJson(doc, payload);
    
    if (doc["status"] == "success") {
      JsonArray networks = doc["networks"];
      int count = networks.size();
      
      if (count > 0) {
        if (dynamicNetworks != nullptr) delete[] dynamicNetworks;
        
        dynamicNetworks = new WiFiNetwork[count];
        numDynamicNetworks = count;
        
        for (int i = 0; i < count; i++) {
          dynamicNetworks[i].ssid = networks[i]["ssid"].as<String>();
          dynamicNetworks[i].password = networks[i]["password"].as<String>();
          dynamicNetworks[i].priority = networks[i]["priority"];
        }
        
        Serial.println("Fetched " + String(numDynamicNetworks) + " WiFi networks from admin panel");
        usingDynamicNetworks = true;
      }
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
    Serial.println("WiFi lost! Trying networks...");

    // Try dynamic networks first if available
    if (usingDynamicNetworks && dynamicNetworks != nullptr && numDynamicNetworks > 0) {
      for (int attempt = 0; attempt < numDynamicNetworks; attempt++)
      {
        WiFi.disconnect();
        Serial.print("Trying dynamic: ");
        Serial.println(dynamicNetworks[attempt].ssid);

        WiFi.begin(dynamicNetworks[attempt].ssid.c_str(), dynamicNetworks[attempt].password.c_str());

        int retries = 0;
        while (WiFi.status() != WL_CONNECTED && retries < 15)
        {
          delay(500);
          Serial.print(".");
          retries++;
        }

        if (WiFi.status() == WL_CONNECTED)
        {
          Serial.print("\nConnected to dynamic: ");
          Serial.println(dynamicNetworks[attempt].ssid);
          return;
        }
        Serial.println(" Failed!");
      }
    }

    // Fallback to hardcoded networks
    for (int attempt = 0; attempt < numFallbackNetworks; attempt++)
    {
      WiFi.disconnect();
      Serial.print("Trying fallback: ");
      Serial.println(fallbackNetworks[currentNetworkIndex].ssid);

      WiFi.begin(fallbackNetworks[currentNetworkIndex].ssid.c_str(), fallbackNetworks[currentNetworkIndex].password.c_str());

      int retries = 0;
      while (WiFi.status() != WL_CONNECTED && retries < 15)
      {
        delay(500);
        Serial.print(".");
        retries++;
      }

      if (WiFi.status() == WL_CONNECTED)
      {
        Serial.print("\nConnected to fallback: ");
        Serial.println(fallbackNetworks[currentNetworkIndex].ssid);
        
        // Try to fetch dynamic networks for next time
        fetchWiFiNetworks();
        return;
      }

      Serial.println(" Failed!");
      currentNetworkIndex = (currentNetworkIndex + 1) % numFallbackNetworks;
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
  if (!f) return;
  f.println(String(totalEnergy, 6));
  f.println(String(peakPower, 2));
  f.println(String(totalCarbon, 6));
  f.println(String(totalCost, 2));
  f.close();
}

void loadAccumulatedData()
{
  if (!SPIFFS.exists("/accumulated.txt")) return;
  File f = SPIFFS.open("/accumulated.txt", FILE_READ);
  if (!f) return;
  if (f.available()) totalEnergy = f.readStringUntil('\n').toFloat();
  if (f.available()) peakPower = f.readStringUntil('\n').toFloat();
  if (f.available()) totalCarbon = f.readStringUntil('\n').toFloat();
  if (f.available()) totalCost = f.readStringUntil('\n').toFloat();
  f.close();
  Serial.println("Restored accumulated data from storage.");
}

// =========================================================
// SAVE FAILED PAYLOAD (SPIFFS)
// =========================================================
void saveToQueue(String payload)
{
  File f = SPIFFS.open("/queue.txt", FILE_APPEND);
  if (!f) {
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
  if (!SPIFFS.exists("/queue.txt") || WiFi.status() != WL_CONNECTED) return;

  File f = SPIFFS.open("/queue.txt", FILE_READ);
  if (!f) return;

  Serial.println("\nTrying to resend queued data...");
  String tempLines = "";

  HTTPClient http;
  http.begin(supabaseUrl);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", supabaseApiKey);
  http.addHeader("Authorization", String("Bearer ") + supabaseApiKey);
  http.setTimeout(5000);

  while (f.available())
  {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() < 5) continue;

    Serial.print("Re-sending: ");
    Serial.println(line);

    int code = http.POST(line);

    if (code == 201) {
      Serial.println("Re-uploaded successfully!");
    } else {
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
  if (tempLines.length() > 0) {
    File newF = SPIFFS.open("/queue.txt", FILE_WRITE);
    if (newF) {
      newF.print(tempLines);
      newF.close();
    }
  } else {
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

  if (WiFi.status() != WL_CONNECTED) {
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

  if (httpCode != 201) {
    saveToQueue(payload);
  } else {
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
  
  // Disable watchdog completely
  disableCore0WDT();
  disableCore1WDT();

  if (!SPIFFS.begin(true))
    Serial.println("SPIFFS Mount Failed!");

  pzemSerial.begin(PZEM_BAUD, SERIAL_8N1, PZEM_RX, PZEM_TX);

  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  ensureWiFiConnected();

  syncTime();
  
  // Fetch WiFi networks from admin panel
  fetchWiFiNetworks();

  // Load accumulated data if device was reset (for blackout protection)
  loadAccumulatedData();
  deviceWasReset = false;

  Serial.println("ESP32 setup complete with dynamic WiFi management!");
}

// =========================================================
// MAIN LOOP
// =========================================================
void loop()
{
  ensureWiFiConnected();
  
  // Try to resend any queued data
  resendQueue();
  
  // Your existing sensor reading and data processing code goes here
  // ...
  
  delay(10000); // 10 second delay
}