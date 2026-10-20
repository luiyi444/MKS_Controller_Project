#include <Arduino.h>

// --- ASIGNACIÓN DE PINES ---
const int READ_PIN = 34;        // GPIO 34: Entrada analógica (Divisor 10k/18k desde Pin 2 MKS)
const int DAC_PIN = 25;         // GPIO 25: Salida Set Point analógica (Directo a Pin 8 MKS)
const int VALVE_CLOSE_PIN = 26;   // GPIO 26: Control de cierre forzado (Directo a Pin 3 MKS)

// --- CONFIGURACIÓN DEL DIVISOR DE VOLTAJE ---
const bool USA_DIVISOR = true;              
const float DIVIDER_RATIO = 28.0 / 18.0;     // Factor del divisor (10k / 18k = 1.555)

// --- PARÁMETROS DEL CONTROLADOR MKS (5000 SCCM N2) ---
const float FS_N2_SCCM = 5000.0;            // Escala nominal completa de Nitrógeno
const float GCF_ARGON = 1.41;               // Factor de Corrección de Gas para Argón
const float ZERO_OFFSET_V = 0.140;          // Desviación de cero en reposo (~0.14V)

// --- VARIABLES GLOBALES ---
float targetArgonSccm = 0.0;                // Flujo objetivo en sccm de Argón
int currentDacVal = 0;                      // Valor enviado al DAC (0 a 255)

void setup() {
  Serial.begin(115200);

  // Configurar resolución y rango del ADC del ESP32
  analogSetPinAttenuation(READ_PIN, ADC_11db);

  // Configurar pin de cierre forzado de válvula (Pin 3 MKS)
  pinMode(VALVE_CLOSE_PIN, OUTPUT);
  digitalWrite(VALVE_CLOSE_PIN, LOW);       // Fuerza el cierre completo en inicio

  // Salida Set Point inicial en 0V
  dacWrite(DAC_PIN, 0);

  Serial.println("\n==================================================");
  Serial.println("   CONTROL MKS 5000 SCCM (N2) -> USO EN ARGÓN");
  Serial.println("==================================================");
  Serial.println("Escribe el flujo deseado de Argón en sccm y presiona Enter.");
  Serial.println("Ejemplos de comando: 500 , 1200 , 2500 , 0");
  Serial.println("--------------------------------------------------\n");
}

void loop() {
  // 1. RECEPCIÓN DE COMANDOS DESDE EL MONITOR SERIE
  if (Serial.available() > 0) {
    float inputVal = Serial.parseFloat();
    
    // Limpiar caracteres sobrantes del buffer
    while (Serial.available() > 0) {
      Serial.read();
    }

    if (inputVal >= 0) {
      targetArgonSccm = inputVal;

      if (targetArgonSccm == 0.0) {
        // CORTE TOTAL DE EMISIÓN DE GAS
        dacWrite(DAC_PIN, 0);
        digitalWrite(VALVE_CLOSE_PIN, LOW); // Activa cierre de seguridad en Pin 3 del MKS
        Serial.println("\n>>> VÁLVULA CERRADA (SetPoint = 0 sccm)");
      } else {
        // MODO AUTOMÁTICO DE CONTROL
        digitalWrite(VALVE_CLOSE_PIN, HIGH); // Desactiva el cierre forzado (Pin 3 liberado)

        // a) Convertir sccm de Argón a equivalente de N2
        float targetN2Sccm = targetArgonSccm / GCF_ARGON;

        // b) Calcular voltaje objetivo para el MKS (0 a 5.0 V)
        float targetVoltsMKS = (targetN2Sccm / FS_N2_SCCM) * 5.0;

        // c) Limitar al máximo del DAC nativo del ESP32 (3.3 V max = ~4653 sccm Argón)
        if (targetVoltsMKS > 3.3) {
          Serial.println("\n[AVISO] Salida limitada al máximo permitido por el DAC del ESP32 (3.3 V / 4653 sccm Ar)");
          targetVoltsMKS = 3.3;
        }

        // d) Escalar a 8 bits para dacWrite (0 a 255 -> 0 a 3.3 V)
        currentDacVal = (targetVoltsMKS / 3.3) * 255.0;
        if (currentDacVal > 255) currentDacVal = 255;
        if (currentDacVal < 0) currentDacVal = 0;

        dacWrite(DAC_PIN, currentDacVal);

        Serial.print("\n>>> NUEVO SET POINT: ");
        Serial.print(targetArgonSccm, 1);
        Serial.print(" sccm Argón | Voltaje SetPoint MKS: ");
        Serial.print(targetVoltsMKS, 3);
        Serial.println(" V");
      }
      Serial.println("--------------------------------------------------");
    }
  }

  // 2. LECTURA PROMEDIADA DEL SENSOR (MKS Pin 2 -> Divisor -> GPIO 34)
  long sumaADC = 0;
  const int MUESTRAS = 50;
  for (int i = 0; i < MUESTRAS; i++) {
    sumaADC += analogRead(READ_PIN);
    delay(2);
  }
  float rawADCProm = (float)sumaADC / MUESTRAS;

  // Convertir lectura ADC a voltaje en GPIO 34 (0 a 3.3 V)
  float voltageESP = (rawADCProm / 4095.0) * 3.3;

  // Reconstruir el voltaje real que emite el Pin 2 del MKS (0 a 5.0 V)
  float voltageMKS = USA_DIVISOR ? (voltageESP * DIVIDER_RATIO) : voltageESP;

  // Restar la desviación de cero en reposo
  float voltageCorregido = voltageMKS - ZERO_OFFSET_V;
  if (voltageCorregido < 0.0) {
    voltageCorregido = 0.0;
  }

  // 3. CÁLCULO DE CAUDAL MEDIDO EN SCCM
  float measuredN2Sccm = (voltageCorregido / 5.0) * FS_N2_SCCM;
  float measuredArgonSccm = measuredN2Sccm * GCF_ARGON;

  // 4. MONITOREO EN CONSOLA
  Serial.print("Objetivo Ar: ");
  Serial.print(targetArgonSccm, 0);
  Serial.print(" sccm | V_MKS: ");
  Serial.print(voltageMKS, 3);
  Serial.print(" V | Flujo Medido (N2): ");
  Serial.print(measuredN2Sccm, 1);
  Serial.print(" sccm | Flujo Medido (Argón): ");
  Serial.print(measuredArgonSccm, 1);
  Serial.println(" sccm");

  delay(500);
}