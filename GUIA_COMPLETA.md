# Guía completa: Kinect v2 en Fedora Linux con libfreenect2

Guía pública para compilar, validar y comenzar a usar una **Kinect v2 / Xbox One** con [libfreenect2](https://github.com/OpenKinect/libfreenect2.git). El identificador USB del sensor es `045e:02c4`.

> **Ruta validada en este equipo:** Fedora Linux 44 x86_64 con kernel `7.2.2-cachyos1.fc44.x86_64`. Es evidencia de una ruta concreta, no una garantía para todas las versiones de Fedora ni otras distribuciones.

> **Alcance:** Kinect v2 únicamente. Quedan fuera `libfreenect` para Kinect v1, OpenNI 1.5, SensorKinect, NITE, Java 6 y Qt4.

## Cómo usar los bloques de comandos

Todos los bloques marcados como `bash` deben copiarse y ejecutarse en una terminal compatible con Bash, un bloque a la vez y desde el directorio indicado inmediatamente antes del bloque. Un bloque de una sola línea contiene un comando; un bloque de varias líneas es una secuencia o un script de Bash y debe copiarse y ejecutarse completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

Los bloques que incluyen `sudo` solicitarán su contraseña de usuario. Nunca pegue una contraseña en la terminal ni en esta guía.

## Índice

- [Ruta rápida](#ruta-rápida)
- [Puntos de control](#puntos-de-control)
- [Preflight USB](#preflight-usb)
- [Instalación y compilación](#instalación-y-compilación)
- [Permisos USB persistentes](#permisos-usb-persistentes)
- [Validación de captura](#validación-de-captura)
- [Resolución de problemas](#resolución-de-problemas)
- [Comenzar a desarrollar](#comenzar-a-desarrollar)
- [Explorador PyQt6 y binding Python](#explorador-pyqt6-y-binding-python)

## Ruta rápida

1. Conecte el sensor **directamente** a un puerto USB 3 SuperSpeed y complete el [preflight USB](#preflight-usb).
2. Instale dependencias, clone el repositorio oficial y compile con la ruta CPU/OpenGL validada.
3. Instale la regla `udev`, recargue las reglas y **desconecte y reconecte físicamente** la Kinect.
4. Ejecute `Protonect` desde `build/bin` durante 30 segundos.
5. Después de cualquier cambio de USB, permisos o entorno, vuelva a ejecutar `Protonect` antes de desarrollar una aplicación.

## Puntos de control

| Punto       | Resultado que debe confirmar                                                      |
| ----------- | --------------------------------------------------------------------------------- |
| Hardware    | `lsusb` identifica `045e:02c4`.                                                   |
| Enlace      | `lsusb -t` muestra la Kinect a `5000M` o más.                                     |
| Compilación | CMake configura y `cmake --build` termina correctamente.                          |
| Permisos    | La regla `udev` está instalada; tras reconectar, el nodo USB muestra modo `0666`. |
| Captura     | `Protonect` abre el dispositivo y muestra procesadores RGB, IR y profundidad.     |

## Preflight USB

Desde cualquier directorio, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden. Ejecute estas comprobaciones **antes de cualquier otro comando**:

```bash
lsusb
lsusb -t
lsusb -d 045e:02c4
```

Condiciones esperadas:

- La identidad USB esperada es `ID 045e:02c4`; por ejemplo, `lsusb` puede mostrar:

  ```text
  Bus 004 Device 002: ID 045e:02c4 Microsoft Corp. Xbox NUI Sensor
  ```

- Los números `Bus` y `Device` varían entre equipos y en cada reconexión; solo `ID 045e:02c4` identifica la Kinect.
- `lsusb -t` muestra el enlace de ese dispositivo a `5000M` o más.
- La Kinect necesita una conexión USB 3 SuperSpeed directa. No puede operar a USB 2 (`480M`) ni a través de un concentrador USB 2.

No copie ni codifique de forma fija los números de bus o dispositivo en comandos o scripts.

Si aparece `480M`, cambie físicamente el cable o el puerto por una conexión directa SuperSpeed y repita `lsusb -t`. No continúe con la compilación o el diagnóstico de software mientras el enlace no cumpla esta condición.

## Instalación y compilación

### Instalar dependencias

Desde cualquier directorio, ejecute este comando en la terminal. Solicitará su contraseña de usuario; nunca la pegue en la terminal ni en este README.

```bash
sudo dnf install cmake gcc-c++ make pkgconf-pkg-config libusb1-devel libjpeg-turbo-devel turbojpeg-devel glfw-devel git
```

### Obtener el código fuente oficial

Desde cualquier directorio, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

```bash
git clone https://github.com/OpenKinect/libfreenect2.git ~/kinectv2
cd ~/kinectv2
```

### Configurar, compilar e instalar en el perfil de usuario

Desde `~/kinectv2`, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$HOME/.local" -DENABLE_CUDA=OFF
cmake --build build -j"$(nproc)"
cmake --install build
```

La ruta CPU/OpenGL con `-DENABLE_CUDA=OFF` es la ruta portátil validada. Si su versión de CUDA y su toolkit son compatibles con el compilador GCC instalado y dispone de todos los encabezados y dependencias necesarios, puede quitar esa opción para compilar con CUDA.

### Fallos de dependencias de CMake

| Mensaje o condición             | Acción                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------- |
| Falta `libusb`                  | Instale `libusb1-devel`: `sudo dnf install libusb1-devel`.                      |
| Falta TurboJPEG o `turbojpeg.h` | Instale ambos paquetes: `sudo dnf install libjpeg-turbo-devel turbojpeg-devel`. |

CMake no puede continuar hasta que `turbojpeg.h` exista y sea detectable. Después de instalar paquetes, vuelva a ejecutar el comando `cmake -S . -B build ...`.

## Permisos USB persistentes

Configure y compruebe el acceso USB con este procedimiento desde `~/kinectv2`:

1. Copie la regla oficial de `udev`:

   Desde `~/kinectv2`, ejecute este comando en la terminal. Solicitará su contraseña de usuario; nunca la pegue en la terminal ni en este README.

   ```bash
   sudo cp platform/linux/udev/90-kinect2.rules /etc/udev/rules.d/
   ```

2. Recargue las reglas y active el cambio:

   Desde `~/kinectv2`, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden. Solicitará su contraseña de usuario; nunca la pegue en la terminal ni en este README.

   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

3. **Desconecte y vuelva a conectar físicamente** la Kinect. Este paso es necesario para que la regla se aplique al dispositivo.

4. Compruebe que la Kinect puede abrirse ejecutando una captura de prueba:

   Desde `~/kinectv2`, ejecute este comando en la terminal.

   ```bash
   timeout 30s build/bin/Protonect
   ```

5. Si Protonect muestra `LIBUSB_ERROR_ACCESS`, repita la instalación de la regla y la secuencia de desconexión y reconexión. También confirme que el sensor esté conectado directamente a un puerto USB 3 SuperSpeed.

## Validación de captura

Primero pruebe la compilación sin depender de la instalación:

Desde `~/kinectv2`, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

```bash
cd ~/kinectv2
timeout 30s build/bin/Protonect
```

Durante una captura sana, los registros deben indicar que el dispositivo fue detectado y abierto, `TurboJpegRgbPacketProcessor` para RGB y `OpenGLDepthPacketProcessor` para IR/profundidad. Si el programa transmite continuamente hasta que vence el límite, el código de salida `124` es esperado: lo devuelve `timeout`.

La instalación de Linux de este proyecto instala la biblioteca, los encabezados y la configuración de CMake, pero sus reglas de instalación no instalan `Protonect`. No suponga una ruta como `$HOME/.local/bin/Protonect`; localícelo primero si su configuración o una versión posterior sí lo instaló:

Desde cualquier directorio, ejecute este comando en la terminal.

```bash
find "$HOME/.local" -type f -name Protonect -print
```

Ejecute únicamente la ruta que devuelva ese comando. Si no devuelve ninguna, mantenga la prueba desde `build/bin/Protonect`.

Para recopilar diagnóstico USB limitado a 30 segundos:

Desde cualquier directorio, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

```bash
cd ~/kinectv2
LIBUSB_DEBUG=3 timeout 30s build/bin/Protonect
```

Revise y elimine datos sensibles o salida no acotada antes de publicar registros de depuración.

## Resolución de problemas

### El enlace muestra `480M`

Cambie físicamente a un cable y puerto SuperSpeed directos; no use un concentrador USB 2. Después, confirme de nuevo:

Desde cualquier directorio, ejecute este comando en la terminal.

```bash
lsusb -t
```

### `LIBUSB_ERROR_ACCESS`

La regla puede no haberse aplicado al dispositivo actual. Repita la instalación de la regla, recargue `udev` y reconecte físicamente la Kinect; después ejecute `timeout 30s build/bin/Protonect` desde `~/kinectv2`.

### `LIBUSB_ERROR_BUSY` en `IrInterfaceId`

Solo si aparece ese error, `snd-usb-audio` puede haber tomado interfaces de la Kinect. El siguiente bloque es un script completo de Bash: descubre la topología actual mediante `045e:02c4`, lista exclusivamente las interfaces vinculadas a `snd-usb-audio`, las desvincula de forma temporal, prueba `Protonect` y vuelve a vincular exactamente esas interfaces al salir. No realiza cambios permanentes. Desde cualquier directorio, cópielo y ejecútelo completo como una sola unidad en la terminal; no ejecute líneas seleccionadas fuera de orden. Solicitará su contraseña de usuario; nunca la pegue en la terminal ni en este README.

```bash
cd ~/kinectv2
mapfile -t KINECT_PATHS < <(
  for device in /sys/bus/usb/devices/*; do
    [ -r "$device/idVendor" ] && [ -r "$device/idProduct" ] || continue
    [ "$(tr -d '\n' < "$device/idVendor")" = "045e" ] || continue
    [ "$(tr -d '\n' < "$device/idProduct")" = "02c4" ] || continue
    basename "$device"
  done
)

if [ "${#KINECT_PATHS[@]}" -ne 1 ]; then
  printf 'Se esperaba exactamente una Kinect 045e:02c4; se encontraron: %s\n' "${#KINECT_PATHS[@]}" >&2
  exit 1
fi

KINECT_PATH="${KINECT_PATHS[0]}"
mapfile -t AUDIO_INTERFACES < <(
  for interface in /sys/bus/usb/devices/"${KINECT_PATH}":1.*; do
    [ -e "$interface" ] || continue
    driver="$(readlink -f "$interface/driver" 2>/dev/null || true)"
    [ "$(basename "$driver")" = "snd-usb-audio" ] && basename "$interface"
  done
)

printf 'Ruta USB detectada: %s\n' "$KINECT_PATH"
printf 'Interfaces snd-usb-audio: %s\n' "${AUDIO_INTERFACES[*]:-ninguna}"
[ "${#AUDIO_INTERFACES[@]}" -gt 0 ] || { printf 'No hay interfaces de audio para desvincular.\n' >&2; exit 1; }

for interface in "${AUDIO_INTERFACES[@]}"; do
  printf '%s' "$interface" | sudo tee /sys/bus/usb/drivers/snd-usb-audio/unbind >/dev/null
done

restore_audio() {
  for interface in "${AUDIO_INTERFACES[@]}"; do
    printf '%s' "$interface" | sudo tee /sys/bus/usb/drivers/snd-usb-audio/bind >/dev/null
  done
}
trap restore_audio EXIT INT TERM

timeout 30s build/bin/Protonect
PROTONECT_STATUS=$?
exit "$PROTONECT_STATUS"
```

El procedimiento es temporal y específico de la topología detectada. No copie identificadores de interfaz de otro equipo.

### Errores al abrir USB o relacionados con U1

Primero confirme SuperSpeed con `lsusb -t`. Solo después recopile información acotada para analizarla, sin atribuir el fallo a una causa específica:

Desde cualquier directorio, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

```bash
lsusb -t
lspci -nnk
cd ~/kinectv2
LIBUSB_DEBUG=3 timeout 30s build/bin/Protonect
```

Redacte información sensible antes de compartir la salida.

## Comenzar a desarrollar

Tras `cmake --install build` con `CMAKE_INSTALL_PREFIX="$HOME/.local"`, las reglas CMake de este proyecto instalan la biblioteca en `$HOME/.local/lib`, los encabezados en `$HOME/.local/include` y la configuración del paquete en `$HOME/.local/lib/cmake/freenect2`. Confírmelo en su instalación con:

Desde cualquier directorio, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

```bash
find "$HOME/.local/include" -type f -path '*/libfreenect2/*' -print
find "$HOME/.local/lib" -type f \( -name 'libfreenect2.so' -o -name 'libfreenect2.so.*' \) -print
find "$HOME/.local/lib/cmake" -type f -name 'freenect2Config.cmake' -print
```

Para ejecutar una aplicación enlazada dinámicamente en la sesión actual, prefiera una configuración por usuario:

Desde cualquier directorio, ejecute este comando en la terminal.

```bash
export LD_LIBRARY_PATH="$HOME/.local/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

Como alternativa, un administrador puede añadir la ruta de biblioteca mediante un archivo en `/etc/ld.so.conf.d/` y ejecutar `ldconfig`; es una decisión de alcance global que requiere `sudo`, por lo que no es la opción predeterminada de esta guía.

Antes de configurar un proyecto externo, descubra la ruta real del paquete:

Desde cualquier directorio, ejecute este comando en la terminal.

```bash
find "$HOME/.local" -type f -name freenect2Config.cmake -print
```

Use la ruta de directorio que contenga el archivo encontrado para configurar el proyecto externo; sustituya el marcador solo después de descubrirlo:

Desde cualquier directorio, copie y ejecute este bloque completo como una sola unidad en la terminal. No ejecute líneas seleccionadas fuera de orden.

```bash
cmake -S /ruta/al/proyecto -B /ruta/al/proyecto/build -Dfreenect2_DIR="/ruta/devuelta/por/find"
cmake --build /ruta/al/proyecto/build -j"$(nproc)"
```

La integración concreta depende del proyecto consumidor. Valide primero `Protonect` tras cada cambio de USB o entorno. Para explorar las capturas y consumirlas desde Python, continúe con la aplicación siguiente.

## Explorador PyQt6 y binding Python

`app/main.py` es una aplicación de escritorio para probar RGB, infrarrojo, profundidad, profundidad corregida, color registrado y parámetros de calibración. Usa el binding comunitario [pylibfreenect2](https://github.com/r9y9/pylibfreenect2) sobre la misma biblioteca C++ instalada. Se verificó con **Python 3.12, NumPy 1.26, Cython 3 y PyQt6**. El binding original solo declaraba compatibilidad hasta Python 3.5; este proyecto incluye dos parches aplicados en orden para esa versión y para exponer funciones C++ adicionales.

La interfaz muestra las capacidades de imagen disponibles en `libfreenect2`; **no** proporciona audio, gestos ni seguimiento de esqueleto. Solo un programa puede abrir el Kinect a la vez: cierre `Protonect` antes de pulsar **Start capture**.

### Preparación

Los comandos siguientes se ejecutan desde la **raíz de este repositorio** (el directorio con `environment.yml` y `app/`). Si ya tiene `libfreenect2/` y `pylibfreenect2/` descargados aquí, no vuelva a clonarlos ni aplique dos veces los parches.

Para una instalación nueva de la aplicación, después de completar el preflight USB y los paquetes Fedora de esta guía, copie y ejecute **el bloque completo** en una terminal Bash:

```bash
git clone https://github.com/OpenKinect/libfreenect2.git libfreenect2
cmake -S libfreenect2 -B libfreenect2/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PWD/libfreenect2/install" -DENABLE_CUDA=OFF
cmake --build libfreenect2/build -j"$(nproc)"
cmake --install libfreenect2/build
git clone https://github.com/r9y9/pylibfreenect2.git pylibfreenect2
git -C pylibfreenect2 apply ../patches/pylibfreenect2-python312.patch
git -C pylibfreenect2 apply ../patches/pylibfreenect2-extra-api.patch
```

Si es una instalación nueva y todavía no instaló la regla `udev`, copie `libfreenect2/platform/linux/udev/90-kinect2.rules` a `/etc/udev/rules.d/`, recárguela y reconecte físicamente el sensor como se explica en [Permisos USB persistentes](#permisos-usb-persistentes).

Instale el entorno aislado y el binding. Ejecute este **bloque completo** desde la misma raíz; no requiere `sudo`:

```bash
micromamba create -y -f environment.yml
LIBFREENECT2_INSTALL_PREFIX="$PWD/libfreenect2/install" micromamba run -n kinectv2-dev python -m pip install --no-build-isolation --no-deps -e ./pylibfreenect2
```

Si el entorno `kinectv2-dev` ya existe, actualice las dependencias con `micromamba env update -n kinectv2-dev -f environment.yml` en lugar de `micromamba create`.

### Iniciar y usar

Desde la raíz de este repositorio, ejecute este comando en una terminal con sesión gráfica:

```bash
LD_LIBRARY_PATH="$PWD/libfreenect2/install/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" micromamba run -n kinectv2-dev python app/main.py

env LD_LIBRARY_PATH="$PWD/libfreenect2/install/lib" micromamba run -n kinectv2-dev python app/main.py
```

1. Seleccione la pipeline de procesamiento (`CpuPacketPipeline` por defecto; las demás aparecen solo si la compilación de `libfreenect2` las habilitó).
2. Configure antes de iniciar el rango y los filtros de profundidad, la exposición RGB (automática, semiautomática o manual) y, si lo desea, el LED. Pulse **Start capture**; las pestañas muestran Color, Infrared, Depth, Undistorted y Registered. Haga clic sobre Depth o Undistorted para consultar distancia y coordenadas 3D aproximadas. Detenga la captura para cambiar estos ajustes. La biblioteca acepta la configuración de profundidad antes de arrancar y los comandos de exposición/LED después de inicializar los flujos en este sensor.
3. Active **Extended registration** antes de iniciar si necesita profundidad a resolución de color y el mapa de píxeles color/profundidad. Estos datos se incluyen en el archivo exportado.
4. Pulse **Save frame data (.npz)** para guardar los arrays originales de NumPy (`Color` en BGRA uint8; `Infrared`, `Depth` y `Undistorted` en float32; `Registered` en BGRA uint8). También incluye secuencia y timestamp. Seleccione **Stop capture** antes de usar el Kinect desde otro programa.

En otro proyecto Python con el mismo entorno, los arrays exportados pueden leerse con `numpy.load("archivo.npz")`. Para acceder en vivo, importe `pylibfreenect2` directamente y siga `pylibfreenect2/examples/multiframe_listener.py`: la interfaz utiliza exactamente ese binding, sin servidor ni API intermedia. No conserve vistas NumPy de `Frame.asarray()` después de `listener.release(frames)`; copie los datos primero, como hace `app/capture.py`.

Si aparece `LIBUSB_ERROR_BUSY` tras reconectar el sensor, aplique el procedimiento temporal de [Resolución de problemas](#libusb_error_busy-en-irinterfaceid). Si aparece `LIBUSB_ERROR_ACCESS`, revise la regla `udev` y reconecte. Confirme siempre que `lsusb -t` muestre `5000M` o más.
