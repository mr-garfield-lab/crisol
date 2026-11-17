# Equipo IA V3 — Guía para Windows 11 (PC: Ryzen 5 5600, 32 GB, RTX 3050 8 GB)

> **NO VALIDADO en Windows.** Todo se desarrolló y probó en un contenedor Linux. Esta guía indica cómo
> ejecutarlo y qué puede fallar; los resultados en Windows deben comprobarse allí.

## 1. Requisitos

- **Python 3.11 o posterior**, de python.org. Solo se usa la biblioteca estándar: no hace falta instalar
  paquetes.
- **ZIP de Equipo IA V3** extraído en una carpeta propia (por ejemplo `C:\EquipoIA_V3`), fuera de OneDrive y
  de carpetas sincronizadas.
- **Opcional, para modelos reales:** la versión CUDA de llama.cpp (`llama-server.exe`) y un GGUF de Qwen. NO se
  incluyen, y este proyecto no descarga nada: los obtiene el usuario.

## 2. Verificación (PowerShell, desde la carpeta extraída)

```powershell
cd C:\EquipoIA_V3\equipo_ia_v3
py -B verificar_v3.py              # integridad, pruebas y mutaciones (F0–F9)
py -B verificar_v3.py --completo   # además la línea base de 503 pruebas (F10)
```

Resultado esperado en Linux: «ESTADO GENERAL: CORRECTO». En Windows pueden aparecer diferencias conocidas:

1. **Enlaces simbólicos.** Las fases de mutación (F3–F9) crean un espejo temporal con `os.symlink`, y algunas
   pruebas de seguridad crean enlaces a propósito. En Windows, crear enlaces exige el **Modo de desarrollador** o
   privilegios de administrador. Sin ellos, esas pruebas fallan por `OSError` y no por un defecto. Hay que activar
   el Modo de desarrollador o interpretar esos fallos como no aplicables.
2. **Rutas y `TMPDIR`.** V2-F.1 usa `$TMPDIR/equipo_f2` como laboratorio. Ver `sistema/MIGRACION_WINDOWS.md` y
   `sistema/PLATAFORMAS.md` (documentación original de V2-F.1).
3. **Línea base (F10).** Se generó en Linux. Las diferencias de plataforma aparecerían como CAMBIO o REGRESION y
   habría que revisarlas una a una; la línea base no debe reajustarse sin una causa documentada.

## 3. Modelo local con GPU (estimaciones de la Etapa 6)

```powershell
py -B equipo3.py pc recomendar
py -B equipo3.py pc planificar qwen2.5-coder-7b-q4_k_m --ctx 8192 --gguf C:\modelos\qwen2.5-coder-7b-instruct-q4_k_m.gguf
```

Orden propuesta para el 7B Q4_K_M. Es una ESTIMACIÓN: 28 de 28 capas en la GPU y unos 5431 MiB de VRAM, por
debajo del tope de 6144 MiB del AI Lab Coordinator, que no se modifica.

```powershell
llama-server.exe -m C:\modelos\qwen2.5-coder-7b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -c 8192 -ngl 28 -t 6 --parallel 1
```

- **Un servidor para los tres agentes:** sirve a A1, A2 y A3 por turnos.
- **Comprobar la VRAM real:** con `nvidia-smi` mientras está cargado. Si supera lo estimado, reducir `-ngl` o
  `-c`.
- **Integración con la GPU:** V2-F.1 lanza su propio llama-server sin `-ngl`, porque está pensado para la CPU del
  teléfono. Para usar la GPU hay que lanzar el servidor con la orden de arriba y conectar Equipo IA a él; adaptar
  `servidor.py` exigiría una nueva línea base.

## 4. Uso básico

```powershell
cd sistema
py -B equipo.py demo funcion      # demostración SIMULADA de A1/A2/A3
cd ..
py -B equipo3.py traza importar LAB-001
py -B equipo3.py traza reconstruir LAB-001/E001
py -B equipo3.py traza deliberacion LAB-001/E001
```

## 5. Lo que no se ha validado en Windows

El rendimiento, la VRAM real, Qwen real, la detección del equipo y las rutas largas de Windows.
