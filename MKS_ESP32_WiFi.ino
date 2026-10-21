#include <WiFi.h>
#include <ESPmDNS.h>
#include <Preferences.h>

// ================== CONFIGURACIÓN WiFi ==================
const char* WIFI_SSID = "Paz_Profesores";
const char* WIFI_PASSWORD = "boaFnBV9xS";
const uint16_t TCP_PORT = 5000;
const char* MDNS_HOSTNAME = "mks1179b";

// IP estática opcional (deja USE_STATIC_IP en false para usar DHCP)
const bool USE_STATIC_IP = false;
IPAddress STATIC_IP(192, 168, 1, 50);
IPAddress STATIC_GATEWAY(192, 168, 1, 1);
IPAddress STATIC_SUBNET(255, 255, 255, 0);
IPAddress STATIC_DNS(8, 8, 8, 8);

// --- ASIGNACIÓN DE PINES ---
const int READ_PIN = 34;        // GPIO 34: Entrada analógica (Divisor 10k/18k desde Pin 2 MKS)
const int DAC_PIN = 25;         // GPIO 25: Salida Set Point analógica (Directo a Pin 8 MKS)
const int VALVE_CLOSE_PIN = 26; // GPIO 26: Control de cierre forzado (Directo a Pin 3 MKS)

// --- HARDWARE ANALÓGICO ---
const bool USA_DIVISOR = true;
const float DIVIDER_RATIO = 28.0 / 18.0; // Factor del divisor (10k / 18k = 1.555)
const float MKS_FS_V = 5.0;              // Fondo de escala de la señal MKS (0-5 V)
const float DAC_FS_V = 3.3;              // Fondo de escala del DAC del ESP32

// --- CONFIGURACIÓN POR DEFECTO (se sobreescribe con lo guardado en NVS) ---
const float DEFAULT_FS_SCCM = 5000.0;    // Capacidad de fábrica del controlador (N2)
const float DEFAULT_GCF = 1.41;          // Factor de corrección de gas para Argón
const float DEFAULT_SPAN_K = 1.0;        // Corrección de span

// --- TIEMPOS (bucle no bloqueante) ---
const unsigned long ADC_SAMPLE_MS = 2;       // Periodo de muestreo del ADC
const unsigned long MEASURE_INTERVAL_MS = 500; // Periodo de telemetría
const unsigned long TARE_SETTLE_MS = 1500;   // Asentamiento al tarar cero

// --- LAZO CERRADO (TRIM) ---
const bool TRIM_ENABLED = true;
const float TRIM_DEADBAND_SCCM = 10.0;
const float TRIM_GAIN_COUNTS_PER_SCCM = 0.05;
const int TRIM_MAX_STEP_COUNTS = 8;
const int TRIM_FAULT_DAC_DELTA = 40;
const float TRIM_FAULT_FLOW_SCCM = 3.0;
const unsigned long TRIM_SETTLE_MS = 1500;
const unsigned long TRIM_UPDATE_MS = 800;
const unsigned long TRIM_FAULT_MS = 8000;

// --- ESTADO ---
Preferences configStore;

float fsN2Sccm = DEFAULT_FS_SCCM;
float gcf = DEFAULT_GCF;
float spanK = DEFAULT_SPAN_K;
float zeroVoltage = 0.0;
float maxTargetSccm = 0.0;

float targetArgonSccm = 0.0;
int currentDacVal = 0;
int trimBaseDac = 0;
bool trimActive = false;

float lastVoltageMKS = 0.0;
float lastMeasuredN2 = 0.0;
float lastMeasuredArgon = 0.0;

unsigned long lastAdcMs = 0;
float adcAccumMv = 0.0;
uint32_t adcSamples = 0;

unsigned long lastMeasureMs = 0;
unsigned long lastTargetChangeMs = 0;
unsigned long lastTrimMs = 0;

WiFiServer server(TCP_PORT);
WiFiClient client;
bool serverStarted = false;
bool wifiWasConnected = false;
unsigned long lastWifiAttempt = 0;

// Lee líneas terminadas en salto de línea desde cualquier Stream (USB o TCP).
class LineReader {
  String buffer;

public:
  bool poll(Stream &stream, String &out) {
    while (stream.available() > 0) {
      char c = (char)stream.read();
      if (c == '\n' || c == '\r') {
        if (buffer.length() == 0) continue;
        out = buffer;
        buffer = "";
        return true;
      } else if (buffer.length() < 48) {
        buffer += c;
      }
    }
    return false;
  }
};

LineReader usbReader;
LineReader wifiReader;

void broadcastLine(const String &line) {
  Serial.println(line);
  if (client && client.connected()) {
    client.println(line);
  }
}

void recomputeLimits() {
  maxTargetSccm = DAC_FS_V / MKS_FS_V * fsN2Sccm * gcf;
}

void saveConfig() {
  configStore.begin("mkscfg", false);
  configStore.putFloat("fs", fsN2Sccm);
  configStore.putFloat("gcf", gcf);
  configStore.putFloat("span", spanK);
  configStore.end();
}

void loadConfig() {
  if (configStore.begin("mkscfg", true)) {
    fsN2Sccm = configStore.getFloat("fs", DEFAULT_FS_SCCM);
    gcf = configStore.getFloat("gcf", DEFAULT_GCF);
    spanK = configStore.getFloat("span", DEFAULT_SPAN_K);
    configStore.end();
  }
  if (fsN2Sccm < 1.0) fsN2Sccm = DEFAULT_FS_SCCM;
  if (gcf <= 0.0) gcf = DEFAULT_GCF;
  if (spanK <= 0.0) spanK = DEFAULT_SPAN_K;
  recomputeLimits();
}

void writeDac(int value) {
  currentDacVal = constrain(value, 0, 255);
  dacWrite(DAC_PIN, currentDacVal);
}

float dacVoltage(int counts) {
  return (float)counts / 255.0 * DAC_FS_V;
}

int baseDacForTarget(float targetArgon) {
  float targetN2 = targetArgon / gcf;
  float targetVolts = targetN2 / fsN2Sccm * MKS_FS_V;
  int counts = (int)round(targetVolts / DAC_FS_V * 255.0);
  return constrain(counts, 0, 255);
}

// Muestreo continuo del ADC para promedio sin bloquear el bucle.
void sampleAdc() {
  unsigned long now = millis();
  if (now - lastAdcMs < ADC_SAMPLE_MS) {
    return;
  }
  lastAdcMs = now;
  adcAccumMv += analogReadMilliVolts(READ_PIN);
  adcSamples++;
}

// Entrega el promedio acumulado y reinicia el acumulador.
float takeAverageVoltage() {
  if (adcSamples == 0) {
    return 0.0;
  }
  float mv = adcAccumMv / (float)adcSamples;
  adcAccumMv = 0.0;
  adcSamples = 0;
  float pinVolts = mv / 1000.0;
  return USA_DIVISOR ? pinVolts * DIVIDER_RATIO : pinVolts;
}

float argonFromVoltage(float voltageMKS) {
  float corrected = voltageMKS - zeroVoltage;
  if (corrected < 0.0) {
    corrected = 0.0;
  }
  float flowN2 = corrected / MKS_FS_V * fsN2Sccm;
  return flowN2 * gcf * spanK;
}

void printConfig() {
  char line[192];
  snprintf(line, sizeof(line),
           "CONFIG FS=%.1f sccm | GCF=%.3f | K=%.4f | Cero=%.4f V | MaxArg=%.1f sccm",
           fsN2Sccm, gcf, spanK, zeroVoltage, maxTargetSccm);
  broadcastLine(line);
}

void closeValve(const char *reason) {
  targetArgonSccm = 0.0;
  trimActive = false;
  writeDac(0);
  digitalWrite(VALVE_CLOSE_PIN, LOW);
  lastTargetChangeMs = millis();
  char line[96];
  snprintf(line, sizeof(line), "\n>>> VÁLVULA CERRADA (%s)", reason);
  broadcastLine(line);
}

void applySetpoint(float target) {
  if (target < 0.0) {
    return;
  }
  if (target <= 0.0) {
    closeValve("SetPoint = 0 sccm");
    broadcastLine("--------------------------------------------------");
    return;
  }
  if (target > maxTargetSccm) {
    char warn[128];
    snprintf(warn, sizeof(warn),
             "[AVISO] Objetivo limitado a %.1f sccm por el tope del DAC (%.2f V).",
             maxTargetSccm, DAC_FS_V);
    broadcastLine(warn);
    target = maxTargetSccm;
  }

  targetArgonSccm = target;
  digitalWrite(VALVE_CLOSE_PIN, HIGH);

  trimBaseDac = baseDacForTarget(targetArgonSccm);
  writeDac(trimBaseDac);
  trimActive = TRIM_ENABLED;
  lastTargetChangeMs = millis();
  lastTrimMs = millis();

  char message[160];
  snprintf(message, sizeof(message),
           "\n>>> NUEVO SET POINT: %.1f sccm Argón | Voltaje SetPoint MKS: %.3f V",
           targetArgonSccm, dacVoltage(trimBaseDac));
  broadcastLine(message);
  broadcastLine("--------------------------------------------------");
}

void tareZero() {
  targetArgonSccm = 0.0;
  trimActive = false;
  writeDac(0);
  digitalWrite(VALVE_CLOSE_PIN, LOW);
  delay(TARE_SETTLE_MS);

  adcAccumMv = 0.0;
  adcSamples = 0;
  unsigned long start = millis();
  while (millis() - start < 300) {
    adcAccumMv += analogReadMilliVolts(READ_PIN);
    adcSamples++;
    delay(2);
  }
  float measuredZero = takeAverageVoltage();

  if (measuredZero >= 0.0 && measuredZero < 1.5) {
    zeroVoltage = measuredZero;
    char line[96];
    snprintf(line, sizeof(line), "\n>>> CERO CALIBRADO: %.4f V CON VÁLVULA CERRADA", zeroVoltage);
    broadcastLine(line);
  } else {
    zeroVoltage = 0.0;
    char line[128];
    snprintf(line, sizeof(line),
             "\n[ERROR] Cero fuera de rango: %.3f V. Revise sensor y divisor.",
             measuredZero);
    broadcastLine(line);
  }

  lastTargetChangeMs = millis();
  lastTrimMs = millis();
  lastMeasureMs = millis() - MEASURE_INTERVAL_MS;
}

void printSpan() {
  char line[64];
  snprintf(line, sizeof(line), "\n>>> SPAN ACTUAL: K=%.4f", spanK);
  broadcastLine(line);
}

void setSpan(float referenceFlow) {
  float maxArgon = fsN2Sccm * gcf;
  float minRef = max(1.0f, maxArgon * 0.01f);
  if (referenceFlow < minRef || referenceFlow > maxArgon) {
    char line[128];
    snprintf(line, sizeof(line),
             "\n[ERROR] Referencia de span fuera de rango (%.1f - %.1f sccm).",
             minRef, maxArgon);
    broadcastLine(line);
    return;
  }
  if (targetArgonSccm < minRef || lastMeasuredArgon < minRef * 0.5f) {
    broadcastLine("\n[ERROR] Ajuste un setpoint estable antes de calibrar el span.");
    return;
  }

  float newCorrection = spanK * referenceFlow / lastMeasuredArgon;
  if (newCorrection < 0.2 || newCorrection > 5.0) {
    broadcastLine("\n[ERROR] Corrección de span fuera de rango. Verifique el medidor de referencia.");
    return;
  }

  spanK = newCorrection;
  saveConfig();
  lastTargetChangeMs = millis();
  lastTrimMs = millis();

  char line[160];
  snprintf(line, sizeof(line),
           "\n>>> SPAN CALIBRADO: K=%.4f | Referencia: %.1f sccm | Medido previo: %.1f sccm",
           spanK, referenceFlow, lastMeasuredArgon);
  broadcastLine(line);
}

void resetSpan() {
  spanK = DEFAULT_SPAN_K;
  saveConfig();
  char line[64];
  snprintf(line, sizeof(line), "\n>>> SPAN RESTABLECIDO: K=%.4f", spanK);
  broadcastLine(line);
}

void setCapacity(float value) {
  if (value < 1.0 || value > 30000.0) {
    broadcastLine("\n[ERROR] Capacidad fuera de rango (1 - 30000 sccm).");
    return;
  }
  fsN2Sccm = value;
  recomputeLimits();
  saveConfig();
  char line[96];
  snprintf(line, sizeof(line), "\n>>> CAPACIDAD AJUSTADA: %.1f sccm (N2) | Máx Argón: %.1f sccm",
           fsN2Sccm, maxTargetSccm);
  broadcastLine(line);
  if (targetArgonSccm > 0.0) {
    applySetpoint(min(targetArgonSccm, maxTargetSccm));
  }
}

void setGcf(float value) {
  if (value < 0.1 || value > 10.0) {
    broadcastLine("\n[ERROR] Factor de gas (GCF) fuera de rango (0.1 - 10.0).");
    return;
  }
  gcf = value;
  recomputeLimits();
  saveConfig();
  char line[96];
  snprintf(line, sizeof(line), "\n>>> GCF AJUSTADO: %.3f | Máx Argón: %.1f sccm", gcf, maxTargetSccm);
  broadcastLine(line);
  if (targetArgonSccm > 0.0) {
    applySetpoint(min(targetArgonSccm, maxTargetSccm));
  }
}

void updateTrim(float measuredArgon) {
  if (!trimActive || targetArgonSccm <= 0.0) {
    return;
  }

  unsigned long now = millis();
  if (now - lastTargetChangeMs < TRIM_SETTLE_MS) {
    return;
  }

  bool noFlowResponse = measuredArgon < TRIM_FAULT_FLOW_SCCM &&
                        (abs(currentDacVal - trimBaseDac) >= TRIM_FAULT_DAC_DELTA ||
                         currentDacVal >= 250);
  if (targetArgonSccm > (fsN2Sccm * gcf * 0.01f) && noFlowResponse &&
      now - lastTargetChangeMs > TRIM_FAULT_MS) {
    broadcastLine("\n[ERROR] Sin respuesta de flujo. Revise sensor, válvula y suministro. Válvula cerrada.");
    closeValve("sin respuesta de flujo");
    return;
  }

  if (now - lastTrimMs < TRIM_UPDATE_MS) {
    return;
  }

  float error = targetArgonSccm - measuredArgon;
  float deadband = TRIM_DEADBAND_SCCM;
  if (deadband > targetArgonSccm * 0.02f) {
    deadband = targetArgonSccm * 0.02f;
  }
  if (fabs(error) <= deadband) {
    lastTrimMs = now;
    return;
  }

  int step = (int)(error * TRIM_GAIN_COUNTS_PER_SCCM);
  step = constrain(step, -TRIM_MAX_STEP_COUNTS, TRIM_MAX_STEP_COUNTS);
  if (step == 0) {
    step = (error > 0.0) ? 1 : -1;
  }

  int newDac = constrain(currentDacVal + step, 0, 255);
  if (newDac != currentDacVal) {
    writeDac(newDac);
    lastTrimMs = now;
  }
}

void measureAndReport() {
  lastVoltageMKS = takeAverageVoltage();
  lastMeasuredArgon = argonFromVoltage(lastVoltageMKS);
  lastMeasuredN2 = lastMeasuredArgon / (gcf * spanK);

  updateTrim(lastMeasuredArgon);

  char line[224];
  snprintf(line, sizeof(line),
           "Objetivo Ar: %.0f sccm | V_MKS: %.3f V | Flujo Medido (N2): %.1f sccm | "
           "Flujo Medido (Argón): %.1f sccm | DAC: %d (%.3f V) | Error: %.1f sccm%s",
           targetArgonSccm, lastVoltageMKS, lastMeasuredN2, lastMeasuredArgon,
           currentDacVal, dacVoltage(currentDacVal), targetArgonSccm - lastMeasuredArgon,
           trimActive ? " | TRIM" : "");
  broadcastLine(line);
}

bool isNumeric(const String &line) {
  if (line.length() == 0) {
    return false;
  }
  for (unsigned int i = 0; i < line.length(); i++) {
    char c = line[i];
    if (!(c >= '0' && c <= '9') && c != '.' && c != ',' && c != '-' && c != '+') {
      return false;
    }
  }
  return true;
}

float toFloatArg(String line) {
  line.trim();
  line.replace(',', '.');
  return line.toFloat();
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) {
    return;
  }

  String upper = line;
  upper.toUpperCase();

  if (upper == "T" || upper == "TARE") {
    broadcastLine("\n>>> TARANDO CERO...");
    tareZero();
    return;
  }
  if (upper == "K") {
    printSpan();
    return;
  }
  if (upper == "R" || upper == "RESET") {
    resetSpan();
    return;
  }
  if (upper == "C" || upper == "CONFIG") {
    printConfig();
    return;
  }
  if (upper.startsWith("FS")) {
    setCapacity(toFloatArg(line.substring(2)));
    return;
  }
  if (upper.startsWith("GCF")) {
    setGcf(toFloatArg(line.substring(3)));
    return;
  }
  if (upper.startsWith("K")) {
    setSpan(toFloatArg(line.substring(1)));
    return;
  }

  if (!isNumeric(line)) {
    broadcastLine("\n[ERROR] Comando no reconocido. Use un número, T, K, R, C, FS<cap> o GCF<factor>.");
    return;
  }

  applySetpoint(toFloatArg(line));
}

void handleCommands() {
  String line;
  if (usbReader.poll(Serial, line)) {
    handleCommand(line);
  }
  if (client && client.connected() && wifiReader.poll(client, line)) {
    handleCommand(line);
  }
}

void updateWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      Serial.println();
      Serial.print("[WiFi] Conectado. IP: ");
      Serial.println(WiFi.localIP());
      Serial.print("[WiFi] Servidor TCP en el puerto ");
      Serial.println(TCP_PORT);
      if (MDNS.begin(MDNS_HOSTNAME)) {
        Serial.print("[WiFi] Nombre mDNS: ");
        Serial.print(MDNS_HOSTNAME);
        Serial.println(".local");
      }
    }

    if (!serverStarted) {
      server.begin();
      server.setNoDelay(true);
      serverStarted = true;
    }

    if (!client || !client.connected()) {
      WiFiClient incoming = server.available();
      if (incoming) {
        if (client) {
          client.stop();
        }
        client = incoming;
        client.setNoDelay(true);
        Serial.print("[WiFi] Cliente conectado desde ");
        Serial.println(client.remoteIP());
        broadcastLine(">>> CONECTADO AL CONTROLADOR MKS");
        printConfig();
      }
    }
    return;
  }

  if (wifiWasConnected) {
    wifiWasConnected = false;
    Serial.println("[WiFi] Conexión perdida. Reintentando...");
  }
  if (client) {
    client.stop();
  }
  if (serverStarted) {
    server.stop();
    serverStarted = false;
  }
  wl_status_t status = WiFi.status();
  bool needsRetry = status == WL_DISCONNECTED || status == WL_NO_SSID_AVAIL ||
                    status == WL_CONNECT_FAILED;
  if (needsRetry && millis() - lastWifiAttempt >= 15000) {
    lastWifiAttempt = millis();
    Serial.print("[WiFi] Conectando a ");
    Serial.println(WIFI_SSID);
    if (USE_STATIC_IP) {
      WiFi.config(STATIC_IP, STATIC_GATEWAY, STATIC_SUBNET, STATIC_DNS);
    }
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);

  analogSetPinAttenuation(READ_PIN, ADC_11db);
  analogReadResolution(12);

  pinMode(VALVE_CLOSE_PIN, OUTPUT);
  digitalWrite(VALVE_CLOSE_PIN, LOW);

  dacWrite(DAC_PIN, 0);

  loadConfig();

  Serial.println("\n==================================================");
  Serial.print("   CONTROL MKS ");
  Serial.print(fsN2Sccm, 0);
  Serial.println(" SCCM (N2) -> USO EN ARGÓN");
  Serial.println("   USB 115200 baudios  +  WiFi TCP");
  Serial.println("==================================================");
  Serial.println("Número = flujo de Argón en sccm  |  T = tarar cero");
  Serial.println("K<flujo> = calibrar span  |  R = restablecer K");
  Serial.println("FS<cap> = capacidad del controlador  |  GCF<f> = factor de gas");
  Serial.println("C = ver configuración actual");
  Serial.println("--------------------------------------------------");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  if (USE_STATIC_IP) {
    WiFi.config(STATIC_IP, STATIC_GATEWAY, STATIC_SUBNET, STATIC_DNS);
  }
  lastWifiAttempt = millis();
  Serial.print("[WiFi] Conectando a ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.println("Calibrando cero con la válvula cerrada...");
  tareZero();
  printConfig();
  Serial.println("--------------------------------------------------");
  Serial.println("Listo. Control en lazo cerrado activo.");
  Serial.println("--------------------------------------------------\n");

  lastMeasureMs = millis();
}

void loop() {
  updateWifi();
  handleCommands();
  sampleAdc();

  if (millis() - lastMeasureMs >= MEASURE_INTERVAL_MS) {
    lastMeasureMs = millis();
    measureAndReport();
  }

  delay(1);
}
