/*
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

// ------------------ WiFi Settings ------------------
const char *ssid = "PLDTLANG";
const char *password = "Successed@123";

// ------------------ Supabase Settings ------------------
const char *supabaseUrl = "https://sfweuxojewjwxyzomyal.supabase.co/rest/v1/tbl_energy_record";
const char *supabaseApiKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNmd2V1eG9qZXdqd3h5em9teWFsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMjA0ODEsImV4cCI6MjA3NTU5NjQ4MX0.DiA1tj4Z66oLbiWo0fxGgKEFep-RE_wrybWp_LVwLT0";

// ------------------ Device Settings ------------------
const char *deviceId = "2";

// ------------------ PZEM Settings ------------------
#define PZEM_RX 16
#define PZEM_TX 17
#define PZEM_BAUD 9600
HardwareSerial pzemSerial(1);                   // Serial1
PZEM004Tv30 pzem(pzemSerial, PZEM_RX, PZEM_TX); // Correct constructor

// ------------------ Reading Interval ------------------
const unsigned long READ_INTERVAL = 600000; // 10 minutes
unsigned long lastReadTime = 0;

// NTP Settings
const char *ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 28800; // UTC+8
const int daylightOffset_sec = 0;

// ------------------ Functions ------------------

// Synchronize time via NTP
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

// Send reading to Supabase
void sendToSupabase(float energy_kwh, float peak_power_w, float carbon_kg, float cost_php)
{
    if (WiFi.status() != WL_CONNECTED)
    {
        Serial.println("WiFi not connected!");
        return;
    }

    HTTPClient http;
    http.begin(supabaseUrl);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("apikey", supabaseApiKey);
    http.addHeader("Authorization", String("Bearer ") + supabaseApiKey);

    // Get current time in ISO format
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

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode > 0)
    {
        Serial.print("Supabase HTTP Response: ");
        Serial.println(httpResponseCode);
        Serial.println(payload);
    }
    else
    {
        Serial.print("Error sending to Supabase: ");
        Serial.println(httpResponseCode);
    }

    http.end();
}

// ------------------ Setup ------------------
void setup()
{
    Serial.begin(115200);
    delay(1000);
    Serial.println("ESP32 PZEM-004T Energy Meter -> Supabase");

    // Initialize PZEM serial
    pzemSerial.begin(PZEM_BAUD, SERIAL_8N1, PZEM_RX, PZEM_TX);

    // Connect to WiFi
    Serial.print("Connecting to WiFi");
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());

    // Synchronize time
    syncTime();
}

// ------------------ Main Loop ------------------
void loop()
{
    unsigned long currentMillis = millis();

    if (currentMillis - lastReadTime >= READ_INTERVAL)
    {
        lastReadTime = currentMillis;

        // Read PZEM values
        float voltage = pzem.voltage();
        float current = pzem.current();
        float power = pzem.power();            // instantaneous Watts
        float energy = pzem.energy() / 1000.0; // Wh -> kWh

        // Calculate carbon and cost
        float carbon = energy * 0.475; // kg CO2 per kWh
        float cost = energy * 12.0;    // PHP per kWh

        // Debug output
        Serial.println("\n--- PZEM-004T Reading ---");
        Serial.print("Voltage: ");
        Serial.print(voltage);
        Serial.println(" V");
        Serial.print("Current: ");
        Serial.print(current);
        Serial.println(" A");
        Serial.print("Power: ");
        Serial.print(power);
        Serial.println(" W");
        Serial.print("Energy: ");
        Serial.print(energy);
        Serial.println(" kWh");
        Serial.print("Carbon: ");
        Serial.print(carbon);
        Serial.println(" kgCO2");
        Serial.print("Cost: ");
        Serial.print(cost);
        Serial.println(" PHP");

        // Send to Supabase
        sendToSupabase(energy, power, carbon, cost);
    }

    delay(100);
}
