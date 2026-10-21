# MKS Controller

Interfaz gráfica en Python para controlar y monitorear un controlador de flujo másico MKS mediante un ESP32, por **WiFi (TCP)** o por **puerto serie USB**.

La aplicación permite elegir la **capacidad de fábrica del controlador** (10 a 20000 sccm de N2) y adapta automáticamente el rango de consigna, los presets y la calibración a esa capacidad.

## Requisitos

- Python 3.10 o superior
- Windows, Linux o macOS con soporte para Qt
- ESP32 con el sketch `MKS_ESP32_WiFi.ino` cargado
- Conexión WiFi si se usa el modo inalámbrico, o puerto serie a 115200 baudios, 8N1

Dependencias de Python:

- PyQt6
- pyqtgraph
- pyserial
- numpy

## Instalación

Desde la carpeta del proyecto:

```powershell
python -m pip install -r requirements.txt
```

Si se prefiere instalar manualmente:

```powershell
python -m pip install PyQt6 pyqtgraph pyserial numpy
```

## Firmware del ESP32

1. Ajusta en `MKS_ESP32_WiFi.ino` las credenciales `WIFI_SSID` / `WIFI_PASSWORD`.
2. Opcionalmente activa `USE_STATIC_IP` y define la IP fija para no depender de mDNS/DHCP.
3. Carga el sketch con el Arduino IDE (placa ESP32 Dev Module).
4. Abre el Monitor Serie a 115200 para ver la IP asignada (y `mks1179b.local` si mDNS está disponible).

## Ejecución

```powershell
python MKS_Controller.py
```

1. En la cabecera elige el modo de conexión:
   - **WiFi**: introduce la IP del ESP32 (o `mks1179b.local`) y el puerto TCP (por defecto `5000`).
   - **Serial**: selecciona el puerto COM del ESP32.
2. Pulsa **Conectar**. La aplicación envía la configuración del controlador al ESP32.
3. Selecciona la **capacidad de fábrica** del controlador en la tarjeta **Controlador MKS**.
4. Introduce el flujo de argón deseado y pulsa **Establecer flujo**.

## Uso

- **Capacidad del controlador**: elige el fondo de escala real (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000 o 20000 sccm). El rango de consigna, los presets y la referencia de span se recalculan al instante y se envían al ESP32 como comando `FS`.
- **Establecer flujo**: envía el set point ingresado al ESP32.
- **Presets rápidos**: 0 %, 10 %, 25 %, 50 %, 75 % y 100 % del rango de argón disponible.
- **Cierre de emergencia**: envía `0` al ESP32 y activa el cierre de la válvula.
- **Monitoreo**: muestra flujo medido de argón, voltaje reconstruido del MKS y flujo equivalente de N2.
- **Gráfica**: flujo medido y set point en una ventana deslizante de 60 segundos.
- **Grabar datos en CSV**: guarda las lecturas en la carpeta `logs/` del proyecto.
- **Calibración en tiempo real**: pulsa **Abrir** en la tarjeta **Calibración** para mostrar los controles.
- **Tarado de cero**: el firmware tara el cero al arrancar. Para repetirlo, pulsa **Tarar cero** o envía `T` desde el Monitor Serie con la válvula cerrada.
- **Calibración de span**: introduce el flujo real del medidor de referencia y pulsa **Calibrar span**. El firmware calcula y guarda el nuevo factor `K`.
- **Lazo cerrado**: tras cada cambio de set point, el firmware ajusta el DAC para que el flujo medido alcance el objetivo. La interfaz muestra los errores del dispositivo como eventos en rojo.

## Rango disponible según la capacidad

El DAC del ESP32 está limitado a 3,3 V sobre un fondo de escala MKS de 5 V, de modo que el rango máximo de argón es:

```text
Máx argón (sccm) = (3.3 / 5) × capacidad_N2 × 1.41
```

| Capacidad N2 | Máx. argón aproximado |
|---|---|
| 10 sccm | 9 sccm |
| 100 sccm | 93 sccm |
| 1000 sccm | 931 sccm |
| 5000 sccm | 4653 sccm |
| 20000 sccm | 18612 sccm |

Si el MKS tiene salida/consigna de otro fondo de escala, ajusta `MKS_FS_V` en el firmware.

## Protocolo (serie y WiFi)

| Comando | Acción |
|---|---|
| `0` | Cierra la válvula y lleva el DAC a 0 V |
| `500`, `2500`, `4650.0` | Ajusta el set point de argón en sccm |
| `FS5000` | Configura la capacidad del controlador en 5000 sccm (N2) |
| `GCF1.41` | Configura el factor de corrección de gas (argón = 1.41) |
| `T` o `TARE` | Tara el cero con la válvula cerrada |
| `K` | Muestra el factor de span actual |
| `K2500.0` | Calibra el span usando 2500 sccm como referencia real |
| `R` o `RESET` | Restablece el span a `1.0` |
| `C` o `CONFIG` | Muestra la configuración actual |

El firmware responde con líneas de estado que comienzan por `Objetivo Ar:` y con eventos como `>>> NUEVO SET POINT`, `>>> CERO CALIBRADO`, `>>> SPAN CALIBRADO`, `CONFIG` o `[ERROR]`.

Al conectar, la interfaz envía `FS` y `GCF` para sincronizar el ESP32 con la capacidad seleccionada. La capacidad, el factor de gas y el span se guardan en la memoria NVS del ESP32 y sobreviven reinicios.

## Calibración de span

1. Conecta un medidor de flujo calibrado para argón en serie, aguas abajo del MKS.
2. Deja estabilizar el MKS y el medidor de referencia.
3. Cierra la válvula y pulsa **Tarar cero**. Confirma el evento `CERO CALIBRADO`.
4. Abre el gas y establece un set point estable, por ejemplo el 50 % del rango.
5. Espera a que el flujo se estabilice.
6. En **Calibración**, escribe el flujo real que indica el medidor de referencia y pulsa **Calibrar span**.
7. El firmware calcula `K = K_anterior × referencia / flujo_medido` y lo guarda en NVS. El valor sobrevive reinicios y cambios de alimentación.
8. Verifica a 25 %, 50 % y 75 % del rango. Si el error cambia mucho entre puntos, revisa el cero, el divisor y la linealidad del MKS.
9. Usa **Restablecer K** o el comando `R` para volver al valor por defecto `1.0`.

La calibración de span requiere un flujo estable y un set point de al menos el 1 % de la capacidad. El firmware rechaza referencias fuera de rango o correcciones fuera de `0.2–5.0`.

## Registro CSV

El archivo se crea automáticamente al activar la casilla **Grabar datos en CSV**:

```text
logs/mks_log_AAAAMMDD_HHMMSS.csv
```

Columnas:

| Columna | Descripción |
|---|---|
| `Timestamp` | Fecha y hora de la lectura en formato ISO |
| `Target_Argon` | Set point de argón en sccm |
| `Measured_Argon` | Flujo medido de argón en sccm |
| `Voltage_MKS` | Voltaje reconstruido del MKS en voltios |

## Notas sobre el hardware

- El DAC del ESP32 está limitado a 3,3 V, por lo que el rango máximo de consigna depende de la capacidad configurada (ver tabla anterior).
- La lectura analógica usa GPIO 34 (ADC1), con atenuación de 11 dB, `analogReadMilliVolts` y promedio continuo de muestras sin bloquear el bucle.
- El muestreo del ADC es no bloqueante, de modo que el servidor WiFi/TCP permanece siempre atento a los comandos.
- El firmware tara el cero automáticamente con la válvula cerrada al arrancar. El valor de cero no se guarda en memoria; se recalcula en cada reinicio o al enviar `T`.
- La capacidad, el factor de gas y la corrección de span se guardan en NVS.
- GPIO 34, 35, 36 y 39 son solo de entrada; no deben configurarse como salidas.
- No uses los pines del ADC2 si el Wi-Fi está activo.
- El puerto serie, cuando se usa, se configura a 115200 baudios, 8 bits de datos, sin paridad y 1 bit de parada.

## Solución de problemas

- **No conecta por WiFi**: confirma la IP (o `mks1179b.local`), que el ESP32 y el PC estén en la misma red y el puerto `5000` libre. El Monitor Serie muestra la IP asignada.
- **No aparece el puerto**: pulsa **Actualizar**, revisa el cable USB y confirma que el Monitor Serie de Arduino esté cerrado.
- **Error al abrir el puerto**: el puerto puede estar ocupado por otro programa o el driver USB-UART no está instalado.
- **No llegan lecturas**: verifica la conexión, la capacidad configurada y que el ESP32 esté enviando datos.
- **La válvula no responde**: confirma la conexión del pin 26 del ESP32 al pin 3 del MKS y del pin 25 al pin 8 del MKS.
- **Lecturas inestables**: revisa las masas comunes, el divisor de voltaje y la alimentación del sensor.
- **El flujo no alcanza el set point**: comprueba que el suministro de gas y la válvula estén abiertos y que el MKS reciba la señal de set point. Si aparece `[ERROR] Sin respuesta de flujo`, el firmware cierra la válvula por seguridad.
- **El flujo medido está desviado pero es estable**: repite el tarado con **Tarar cero** y verifica el divisor, `MKS_FS_V` y el factor de gas. Para una corrección de span, compara con un flujo de referencia y usa **Calibrar span**; si la calibración queda mal, pulsa **Restablecer K**.
