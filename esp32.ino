/*
 * GreenWatts ESP32 PZEM-004T Energy Meter Reader
 *
 * This sketch reads voltage and current data from a PZEM-004T energy meter
 * connected via Modbus RTU protocol and sends it to the GreenWatts server.
 *
 * Hardware Connections:
 * PZEM-004T RX -> ESP32 GPIO 16 (RX2)
 * PZEM-004T TX -> ESP32 GPIO 17 (TX2)
 * PZEM-004T GND -> ESP32 GND
 * PZEM-004T VCC -> 5V Power Supply
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <sys/time.h>
#include <SPIFFS.h>

// WiFi Configuration
const char *ssid = "PLDTLANG";
const char *password = "Successed@123";

// Server Configuration
const char *serverUrl = "http://localhost:8000/api/sensor-data"; // Update with your server URL
const char *apiKey = "YOUR_API_KEY";

// Device Configuration
const int deviceId = 1; // Update with your device ID from GreenWatts

// PZEM-004T Configuration
#define PZEM_RX_PIN 16
#define PZEM_TX_PIN 17
#define PZEM_SERIAL Serial2
#define PZEM_BAUD 9600
#define PZEM_SLAVE_ID 1

// Reading interval (milliseconds)
#define READ_INTERVAL 10000 // Read every 10 seconds

// NTP Server for time synchronization
const char *ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 28800; // UTC+8 (Philippines) - change for your timezone
const int daylightOffset_sec = 0; // Daylight saving offset in seconds

// File storage
#define DATA_FILE "/readings.json"

// Global variables
unsigned long lastReadTime = 0;
float voltage = 0.0;
float current = 0.0;
bool dataSentToday = false;
time_t lastSendTime = 0;
int readingCount = 0;

// Synchronize time with NTP server
void syncTime()
{
  Serial.println("Synchronizing time with NTP server...");
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);

  time_t now = time(nullptr);
  int attempts = 0;
  while (now < 24 * 3600 && attempts < 20)
  {
    delay(500);
    Serial.print(".");
    now = time(nullptr);
    attempts++;
  }
  Serial.println();

  struct tm timeinfo = *localtime(&now);
  Serial.print("Current time: ");
  Serial.println(asctime(&timeinfo));
}

// Check if it's midnight (12:00 AM)
bool isMidnight()
{
  time_t now = time(nullptr);
  struct tm *timeinfo = localtime(&now);

  // Check if hour is 0 (midnight) and we haven't sent data yet today
  if (timeinfo->tm_hour == 0 && !dataSentToday)
  {
    return true;
  }

  // Reset flag when it's not midnight anymore
  if (timeinfo->tm_hour != 0)
  {
    dataSentToday = false;
  }

  return false;
}

// Modbus CRC calculation
uint16_t calculateCRC(uint8_t *data, uint8_t length)
{
  uint16_t crc = 0xFFFF;
  for (uint8_t i = 0; i < length; i++)
  {
    crc ^= data[i];
    for (uint8_t j = 0; j < 8; j++)
    {
      if (crc & 0x0001)
      {
        crc = (crc >> 1) ^ 0xA001;
      }
      else
      {
        crc >>= 1;
      }
    }
  }
  return crc;
}

// Read data from PZEM-004T using Modbus RTU
bool readPZEMData()
{
  // Modbus RTU request: Read Input Registers (Function Code 04)
  // Request format: [Slave ID][Function Code][Start Address High][Start Address Low][Quantity High][Quantity Low][CRC Low][CRC High]
  uint8_t request[] = {PZEM_SLAVE_ID, 0x04, 0x00, 0x00, 0x00, 0x0A, 0x00, 0x00};

  // Calculate CRC
  uint16_t crc = calculateCRC(request, 6);
  request[6] = crc & 0xFF;
  request[7] = (crc >> 8) & 0xFF;

  // Clear serial buffer
  while (PZEM_SERIAL.available())
  {
    PZEM_SERIAL.read();
  }

  // Send request
  PZEM_SERIAL.write(request, 8);
  PZEM_SERIAL.flush();

  // Wait for response
  unsigned long startTime = millis();
  uint8_t response[25];
  uint8_t responseIndex = 0;

  while (millis() - startTime < 1000)
  {
    if (PZEM_SERIAL.available())
    {
      response[responseIndex++] = PZEM_SERIAL.read();
      if (responseIndex >= 25)
        break;
    }
  }

  if (responseIndex < 25)
  {
    Serial.println("ERROR: Incomplete response from PZEM-004T");
    return false;
  }

  // Verify CRC
  uint16_t receivedCRC = (response[24] << 8) | response[23];
  uint16_t calculatedCRC = calculateCRC(response, 23);

  if (receivedCRC != calculatedCRC)
  {
    Serial.println("ERROR: CRC mismatch");
    return false;
  }

  // Parse response data
  // Response format: [Slave ID][Function Code][Byte Count][Data...][CRC Low][CRC High]
  // Data: Voltage(2 bytes), Current(2 bytes), Power(2), Energy(2), Frequency(1), Power Factor(1)

  // Extract voltage (bytes 3-4) - in 0.1V units
  voltage = ((response[3] << 8) | response[4]) / 10.0;

  // Extract current (bytes 5-6) - in 0.001A units
  current = ((response[5] << 8) | response[6]) / 1000.0;

  return true;
}

// Store reading to file
void storeReading(float volt, float curr)
{
  if (!SPIFFS.begin(true))
  {
    Serial.println("SPIFFS Mount Failed");
    return;
  }

  // Read existing data
  DynamicJsonDocument doc(8192);
  File file = SPIFFS.open(DATA_FILE, "r");

  if (file && file.size() > 0)
  {
    deserializeJson(doc, file);
    file.close();
  }
  else if (file)
  {
    file.close();
    // Create new readings array if file is empty
    doc.createNestedArray("readings");
  }
  else
  {
    // Create new readings array if file doesn't exist
    doc.createNestedArray("readings");
  }

  // Get or create readings array
  JsonArray readingsArray;
  if (doc.containsKey("readings"))
  {
    readingsArray = doc["readings"];
  }
  else
  {
    readingsArray = doc.createNestedArray("readings");
  }

  // Add new reading to array
  JsonObject reading = readingsArray.createNestedObject();
  reading["voltage"] = volt;
  reading["current"] = curr;
  reading["timestamp"] = (long)time(nullptr);

  // Write back to file
  file = SPIFFS.open(DATA_FILE, "w");
  serializeJson(doc, file);
  file.close();

  readingCount++;
  Serial.print("Reading stored. Total: ");
  Serial.println(readingCount);
}

// Send all collected data to GreenWatts server
void sendDailyDataToServer()
{
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("WiFi not connected");
    return;
  }

  if (!SPIFFS.begin(true))
  {
    Serial.println("SPIFFS Mount Failed");
    return;
  }

  File file = SPIFFS.open(DATA_FILE, "r");
  if (!file || file.size() == 0)
  {
    Serial.println("No data to send");
    if (file)
      file.close();
    return;
  }

  Serial.print("Sending ");
  Serial.print(readingCount);
  Serial.println(" readings to server...");

  // Read data from file
  DynamicJsonDocument fileDoc(4096);
  deserializeJson(fileDoc, file);
  file.close();

  // Create payload for server
  DynamicJsonDocument payload(4096);
  payload["device_id"] = deviceId;
  payload["reading_count"] = readingCount;
  payload["readings"] = fileDoc["readings"];

  String jsonString;
  serializeJson(payload, jsonString);

  Serial.println("Sending data to server:");
  Serial.println(jsonString);

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  int httpResponseCode = http.POST(jsonString);

  if (httpResponseCode > 0)
  {
    Serial.print("HTTP Response code: ");
    Serial.println(httpResponseCode);

    if (httpResponseCode == 200)
    {
      Serial.println("Data sent successfully!");
      // Clear file after successful send
      SPIFFS.remove(DATA_FILE);
      readingCount = 0;
      dataSentToday = true;
      lastSendTime = time(nullptr);
    }
  }
  else
  {
    Serial.print("Error code: ");
    Serial.println(httpResponseCode);
  }

  http.end();
}

// WiFi connection handler
void connectToWiFi()
{
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20)
  {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  }
  else
  {
    Serial.println("\nFailed to connect to WiFi");
  }
}

void setup()
{
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n\nGreenWatts ESP32 PZEM-004T Reader - Daily Data Collection");
  Serial.println("=========================================================");

  // Initialize SPIFFS for file storage
  if (!SPIFFS.begin(true))
  {
    Serial.println("SPIFFS Mount Failed");
  }
  else
  {
    Serial.println("SPIFFS initialized successfully");
  }

  // Initialize PZEM serial connection
  PZEM_SERIAL.begin(PZEM_BAUD, SERIAL_8N1, PZEM_RX_PIN, PZEM_TX_PIN);

  // Connect to WiFi
  connectToWiFi();

  // Synchronize time with NTP server
  delay(2000);
  syncTime();

  Serial.println("System ready. Collecting data throughout the day...");
  Serial.println("Data will be sent at 12:00 AM (midnight)");
}

void loop()
{
  unsigned long currentTime = millis();

  // Read PZEM data at regular intervals
  if (currentTime - lastReadTime >= READ_INTERVAL)
  {
    lastReadTime = currentTime;

    if (readPZEMData())
    {
      Serial.println("\n--- PZEM-004T Data ---");
      Serial.print("Voltage: ");
      Serial.print(voltage);
      Serial.println(" V");
      Serial.print("Current: ");
      Serial.print(current);
      Serial.println(" A");

      // Store the reading
      storeReading(voltage, current);
    }
  }

  // Check if it's midnight and send all collected data
  if (isMidnight())
  {
    Serial.println("\n========== MIDNIGHT - SENDING DAILY DATA ==========");
    sendDailyDataToServer();
    Serial.println("====================================================\n");
  }

  delay(100);
}
