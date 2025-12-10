/*
 * ESP32 PZEM-004T Energy Meter to Supabase (Daily Upload at 1:00 PM)
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

// ------------------ DAILY UPLOAD FLAG ------------------
bool uploadedToday = false;

// ------------------ Accumulators ------------------
float totalEnergy = 0; // kWh
float peakPower = 0;   // W
float totalCarbon = 0; // kg
float totalCost = 0;   // PHP

// ------------------ NTP Settings ------------------
const char *ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 28800; // UTC+8
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
        Serial.println(WiFi.status() == WL_CONNECTED ? "\nWiFi reconnected!" : "\nWiFi reconnect failed!");
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
}

// =========================================================
// SEND TO SUPABASE
// =========================================================
void sendToSupabase(float energy_kwh, float peak_power_w, float carbon_kg, float cost_php)
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
    payload += "\"total_energy_kwh\":" + String(energy_kwh, 3) + ",";
    payload += "\"peak_power_w\":" + String(peak_power_w, 2) + ",";
    payload += "\"carbon_emission_kgco2\":" + String(carbon_kg, 3) + ",";
    payload += "\"cost_estimate\":" + String(cost_php, 2) + ",";
    payload += "\"device_id\":\"" + String(deviceId) + "\"";
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

    WiFi.begin(ssid, password);
    WiFi.setAutoReconnect(true);
    WiFi.persistent(true);

    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi Connected!");

    syncTime();
    resendQueue();
}

// =========================================================
// LOOP
// =========================================================
void loop()
{
    ensureWiFiConnected();

    unsigned long currentMillis = millis();

    // Read PZEM every 1 minute
    if (currentMillis - lastReadTime >= READ_INTERVAL)
    {

        // Calculate actual elapsed time
        unsigned long elapsed = currentMillis - lastReadTime; // in ms
        lastReadTime = currentMillis;

        float voltage = pzem.voltage();
        float current = pzem.current();
        float power = pzem.power();

        // ------------------ Updated energy calculation ------------------
        float deltaEnergy = power * (elapsed / 3600000.0); // W * hours = kWh

        if (deltaEnergy > 0 && deltaEnergy < 1)
        {
            totalEnergy += deltaEnergy;
            totalCarbon += deltaEnergy * 0.475;
            totalCost += deltaEnergy * 12.0;
        }

        if (power > peakPower)
            peakPower = power;

        // ------------------ DEBUG PRINT ------------------
        struct tm timeinfo;
        if (getLocalTime(&timeinfo))
        {
            char timeStr[20];
            strftime(timeStr, sizeof(timeStr), "%H:%M:%S", &timeinfo);
            Serial.print("[");
            Serial.print(timeStr);
            Serial.print("] ");
            Serial.print("Voltage: ");
            Serial.print(voltage);
            Serial.print(" V, ");
            Serial.print("Current: ");
            Serial.print(current);
            Serial.print(" A, ");
            Serial.print("Power: ");
            Serial.print(power);
            Serial.println(" W");
        }
    }

    // Daily upload at exactly 3:00 PM (15:00)
    struct tm timeinfo;
    if (getLocalTime(&timeinfo))
    {
        if (timeinfo.tm_hour == 15 && timeinfo.tm_min == 0)
        {
            if (!uploadedToday)
            {
                Serial.println("\n--- Sending Daily Summary ---");
                sendToSupabase(totalEnergy, peakPower, totalCarbon, totalCost);

                totalEnergy = 0;
                peakPower = 0;
                totalCarbon = 0;
                totalCost = 0;

                uploadedToday = true;
            }
        }
        else
        {
            uploadedToday = false;
        }
    }

    if (WiFi.status() == WL_CONNECTED)
        resendQueue();

    delay(1000);
}
