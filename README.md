# MKS Controller

Interfaz gráfica en Python para controlar y monitorear el controlador de flujo MKS 5000 sccm (N2) mediante un ESP32 por puerto serie.

## Requisitos

- Python 3.10 o superior
- Windows, Linux o macOS con soporte para Qt
- ESP32 con el sketch `Arduino_Code.ino` cargado
- Puerto serie disponible a 115200 baudios, 8N1

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

## Ejecución

1. Conecta el ESP32 por USB.
2. Carga `Arduino_Code.ino` en la ESP32 usando Arduino IDE.
3. Cierra el Monitor Serie de Arduino para liberar el puerto COM.
4. Ejecuta la aplicación:

```powershell
python MKS_Controller.py
```

5. En la barra superior, selecciona el puerto COM del ESP32 y pulsa **Conectar**.
6. Introduce el flujo de argón deseado (0 a 4650 sccm) y pulsa **Establecer flujo**.

> La ESP32 se reinicia al abrir el puerto serie. La aplicación espera aproximadamente un segundo antes de habilitar la comunicación para evitar perder los primeros comandos.

## Uso

- **Establecer flujo**: envía el set point ingresado al ESP32.
- **Presets rápidos**: envían de inmediato 0, 100, 500, 1000, 2500 o 4650 sccm.
- **Cierre de emergencia**: envía `0` al ESP32 y activa el cierre de la válvula.
- **Monitoreo**: muestra flujo medido de argón, voltaje reconstruido del MKS y flujo equivalente de N2.
- **Gráfica**: flujo medido y set point en una ventana deslizante de 60 segundos.
- **Grabar datos en CSV**: guarda las lecturas en la carpeta `logs/` del proyecto.

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

- El DAC del ESP32 está limitado a 3.3 V, por lo que el rango máximo de consigna es de 4650 sccm de argón (aproximadamente el 66 % del fondo de escala del MKS de 5 V).
- La lectura analógica usa GPIO 34 (ADC1), con atenuación de 11 dB y promedio de 50 muestras en el firmware.
- GPIO 34, 35, 36 y 39 son solo de entrada; no deben configurarse como salidas.
- No uses los pines del ADC2 si el Wi-Fi está activo.
- El puerto serie se configura siempre a 115200 baudios, 8 bits de datos, sin paridad y 1 bit de parada.

## Solución de problemas

- **No aparece el puerto**: pulsa **Actualizar**, revisa el cable USB y confirma que el Monitor Serie de Arduino esté cerrado.
- **Error al abrir el puerto**: el puerto puede estar ocupado por otro programa o el driver USB-UART no está instalado.
- **No llegan lecturas**: verifica que el sketch esté cargado, que la velocidad sea 115200 y que el ESP32 esté enviando datos.
- **La válvula no responde**: confirma la conexión del pin 26 del ESP32 al pin 3 del MKS y del pin 25 al pin 8 del MKS.
- **Lecturas inestables**: revisa las masas comunes, el divisor de voltaje y la alimentación del sensor.
