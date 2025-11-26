/*
 * ESP32 PZEM-004T Energy Meter to Supabase (With Offline Queue)
 * ESP32 PZEM-004T Energy Meter to Supabase
 *
 * Hardware Connections:
 * PZEM-004T RX -> ESP32 GPIO 16 (RX2)
 * PZEM-004T TX -> ESP32 GPIO 17 (TX2)
 * PZEM-004T GND -> ESP32 GND
 * PZEM-004T VCC -> 5V Power Supply
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <PZEM004Tv30.h>
#include <time.h>
#include <SPIFFS.h>

// ------------------ WiFi Settings ------------------
const char *ssid = "PLDTLANG";
const char *password = "Successed@123";

// ------------------ Supabase Settings ------------------
const char *supabaseUrl = "https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/tbl_energy_record";
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
const unsigned long READ_INTERVAL = 60000; // 1 minute
unsigned long lastReadTime = 0;

// ------------------ Accumulators ------------------
float totalEnergy = 0;
float peakPower = 0;
float totalCarbon = 0;
float totalCost = 0;
bool sentToday = false;

// ------------------ NTP Settings ------------------
const char *ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 28800;
const int daylightOffset_sec = 0;

// =========================================================
// WIFI AUTO-RECONNECT
// =========================================================
void ensureWiFiConnected()
{
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("WiFi lost! Reconnecting...");

    WiFi.disconnect();
    WiFi.begin(ssid, password);

    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 20)
    {
      delay(500);
      Serial.print(".");
      retries++;
    }

    if (WiFi.status() == WL_CONNECTED)
    {
      Serial.println("\nWiFi reconnected!");
    }
    else
    {
      Serial.println("\nWiFi reconnect failed!");
    }
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
// SAVE FAILED PAYLOAD TO QUEUE (SPIFFS)
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
// RESEND QUEUED DATA
// =========================================================
void resendQueue()
{
  if (!SPIFFS.exists("/queue.txt"))
    return;

  File f = SPIFFS.open("/queue.txt", FILE_READ);
  if (!f)
    return;

  Serial.println("\nTrying to resend queued data...");

  HTTPClient http;
  http.begin(supabaseUrl);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", supabaseApiKey);
  http.addHeader("Authorization", String("Bearer ") + supabaseApiKey);

  bool allSuccess = true;

  while (f.available())
  {
    String line = f.readStringUntil('\n');
    if (line.length() < 5)
      continue;

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
      allSuccess = false;
      break;
    }
  }

  f.close();
  http.end();

  if (allSuccess)
  {
    SPIFFS.remove("/queue.txt");
    Serial.println("Queue cleared.");
  }
  else
  {
    Serial.println("Keeping remaining data in queue.");
  }
}

// =========================================================
// SEND TO SUPABASE (WITH DEBUG + FAIL QUEUE)
// =========================================================
void sendToSupabase(float energy_kwh, float peak_power_w, float carbon_kg, float cost_php)
{
  // Get timestamp
  struct tm timeinfo;
  time_t now = time(nullptr);
  localtime_r(&now, &timeinfo);
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);

  // Build JSON payload
  String payload = "{";
  payload += "\"date\":\"" + String(buf) + "\","; 
  payload += "\"total_energy_kwh\":" + String(energy_kwh, 3) + ",";
  payload += "\"peak_power_w\":" + String(peak_power_w, 2) + ",";
  payload += "\"carbon_emission_kgco2\":" + String(carbon_kg, 3) + ",";
  payload += "\"cost_estimate\":" + String(cost_php, 2) + ",";
  payload += "\"device_id\":\"" + String(deviceId) + "\"";
  payload += "}";

  // Debug print
  Serial.println("\n=== JSON Payload ===");
  Serial.println(payload);
  Serial.println("====================");

  // If WiFi is down → save to queue
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("WiFi is offline — saving data to queue.");
    saveToQueue(payload);
    return;
  }

  // Send to Supabase
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
    Serial.println("Send failed — saving to queue.");
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
  Serial.println("ESP32 PZEM-004T Energy Meter -> Supabase with Offline Queue");

  // Init SPIFFS
  if (!SPIFFS.begin(true))
  {
    Serial.println("SPIFFS Mount Failed!");
  }

  // Init PZEM serial
  pzemSerial.begin(PZEM_BAUD, SERIAL_8N1, PZEM_RX, PZEM_TX);

  // Connect WiFi
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());

  syncTime();

  // Try resending old data on boot
  resendQueue();
}

// =========================================================
// LOOP
// =========================================================
void loop()
{
  ensureWiFiConnected();

  unsigned long currentMillis = millis();

  // Read PZEM every 1 minute and accumulate data
if (currentMillis - lastReadTime >= READ_INTERVAL)
{
    lastReadTime = currentMillis;

    static float lastEnergy = 0;

    float voltage = pzem.voltage();
    float current = pzem.current();
    float power = pzem.power();
    float currentEnergy = pzem.energy() / 1000.0; // kWh (total since first power-up)

    // Calculate only the change since last reading
    if (currentEnergy >= lastEnergy) {
        float deltaEnergy = currentEnergy - lastEnergy;
        totalEnergy += deltaEnergy;
        totalCarbon += deltaEnergy * 0.475;
        totalCost += deltaEnergy * 12.0;
    }

    lastEnergy = currentEnergy;

    if (power > peakPower) peakPower = power;

    // Debug
    Serial.println("\n--- Accumulated PZEM Reading ---");
    Serial.print("Voltage: "); Serial.println(voltage);
    Serial.print("Current: "); Serial.println(current);
    Serial.print("Power: "); Serial.println(power);
    Serial.print("Today's Total Energy: "); Serial.println(totalEnergy);
    Serial.print("Peak Power: "); Serial.println(peakPower);
}

  // Get current time
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo))
  {
    delay(1000);
    return;
  }

  // Send daily summary at 12:00 AM
  if (timeinfo.tm_hour == 0 && timeinfo.tm_min == 0 && !sentToday)
  {
    Serial.println("\n--- Sending Daily Summary at 12:00 AM ---");
    sendToSupabase(totalEnergy, peakPower, totalCarbon, totalCost);

    // Reset accumulators for next day
    totalEnergy = 0;
    peakPower = 0;
    totalCarbon = 0;
    totalCost = 0;

    sentToday = true;
  }
  else if (timeinfo.tm_hour != 0 || timeinfo.tm_min != 0)
  {
    sentToday = false; // Reset flag after midnight
  }

  // Resend queued data if WiFi is connected
  if (WiFi.status() == WL_CONNECTED)
  {
    resendQueue();
  }

  delay(1000); // loop every second
}
