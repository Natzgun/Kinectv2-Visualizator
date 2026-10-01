# Kinect v2 Explorer

Aplicación PyQt6 para ver color, infrarrojo y profundidad del Kinect v2, consultar la calibración y guardar capturas `.npz`. Usa `libfreenect2` mediante `pylibfreenect2`.

## Ejecutar

Conecta el Kinect directamente a un puerto USB 3. Desde **la carpeta que contiene este README** (si estás en `app/`, ejecuta antes `cd ..`), ejecuta estos comandos; sirven tanto en **fish** como en Bash:

```bash
lsusb -d 045e:02c4
lsusb -t
env LD_LIBRARY_PATH="$PWD/libfreenect2/install/lib" micromamba run -n kinectv2-dev python app/main.py
```

El sensor debe aparecer en `lsusb` y estar conectado a `5000M` o más en `lsusb -t`. Cierra `Protonect` u otros programas que usen el Kinect antes de pulsar **Start capture**. Detén la captura antes de desconectarlo.

## Primera instalación

Estos pasos se ejecutan **una sola vez** desde la carpeta de este README, después de instalar las dependencias de compilación indicadas en la [guía completa](GUIA_COMPLETA.md#instalar-dependencias):

```bash
git clone https://github.com/OpenKinect/libfreenect2.git libfreenect2
cmake -S libfreenect2 -B libfreenect2/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PWD/libfreenect2/install" -DENABLE_CUDA=OFF
cmake --build libfreenect2/build --parallel
cmake --install libfreenect2/build

git clone https://github.com/r9y9/pylibfreenect2.git pylibfreenect2
git -C pylibfreenect2 apply ../patches/pylibfreenect2-python312.patch
git -C pylibfreenect2 apply ../patches/pylibfreenect2-extra-api.patch
micromamba create -y -f environment.yml
env LIBFREENECT2_INSTALL_PREFIX="$PWD/libfreenect2/install" micromamba run -n kinectv2-dev python -m pip install --no-build-isolation --no-deps -e ./pylibfreenect2
```

Si los directorios `libfreenect2/` y `pylibfreenect2/` ya existen, **no repitas los clones ni los parches**. Si aún no tienes permisos USB, instala la [regla `udev`](GUIA_COMPLETA.md#permisos-usb-persistentes) y reconecta físicamente el sensor; no necesitas instalar las bibliotecas globalmente.

## Uso

Selecciona un dispositivo, los flujos y una pipeline; ajusta profundidad o exposición antes de iniciar. La pestaña **Capabilities** enumera los métodos exportados y los flujos efectivamente capturados (solo CPU y OpenGL están compilados en esta instalación). Ajusta los **preview FPS** para limitar el trabajo de la interfaz. Activa **Extended registration** si quieres profundidad a resolución de color y el mapa de correspondencia. Haz clic en profundidad para consultar XYZ y el píxel color asociado. **Save frame data (.npz)** guarda arrays originales, metadatos por flujo y calibración para NumPy. Los timestamps crudos usan unidades de 0,125 ms.

### Reconocimiento de manos y gestos

En **Hand analysis**, elige **Gestures** antes de iniciar para reconocer `Closed_Fist`, `Open_Palm`, `Pointing_Up`, `Thumb_Down`, `Thumb_Up`, `Victory` e `ILoveYou` usando `app/gesture_recognizer.task`. El modo **Landmarks** usa `app/hand_landmarker.task` y muestra los 21 puntos de cada mano sin clasificar gestos. Ambos requieren **Color stream**; con **Extended registration** se muestra también la distancia aproximada a la muñeca cuando hay profundidad válida. El resultado y los puntos aparecen en la imagen **Color**; selecciona **Off** para no ejecutar inferencia.

La inferencia usa un hilo independiente y procesa el frame más reciente, descartando frames intermedios si va más lenta que la captura. MediaPipe usa RGB; la profundidad solo complementa el resultado, no forma parte del clasificador de gestos. La señal `GestureThread.results_ready` entrega gestos, puntuaciones, puntos 2D y coordenadas 3D **relativas a la mano**; estas últimas no son posiciones absolutas del Kinect. El reconocedor incluye su propio detector de manos: no ejecutes simultáneamente los dos modelos para la misma imagen. Estos modelos reconocen gestos estáticos predefinidos; gestos de movimiento o clases propias requieren un modelo entrenado para ello. Tras actualizar un entorno existente, ejecuta `micromamba env update -n kinectv2-dev -f environment.yml` desde la raíz y reinicia la aplicación. No necesitas PyTorch para esta función.

La fila **Advanced RGB setting** permite leer/escribir comandos nativos de `ColorSettingCommand` mientras el flujo color está activo. Selecciona **Float** cuando el valor sea de coma flotante (por ejemplo, `GET_FRAME_RATE` devuelve `30.0`; como entero muestra sus bits). Un mensaje «sent» solo confirma que se envió el comando, no que el firmware lo aplicó.

El binding Python también expone parámetros de calibración, registro por punto y replay de paquetes `.depth` crudos; el replay nativo **no** reproduce los `.npz` exportados por esta aplicación y su implementación en C++ está incompleta. No cambies los parámetros de fábrica sin valores calibrados. Consulta `pylibfreenect2/pylibfreenect2/libfreenect2.pyx` para los métodos disponibles.

Si falla la conexión o aparece `LIBUSB_ERROR_BUSY`, consulta la [guía completa de instalación y diagnóstico](GUIA_COMPLETA.md#resolución-de-problemas).
