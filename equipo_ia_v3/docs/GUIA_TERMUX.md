# Equipo IA V3 — Guía para Android con Termux (p. ej. Samsung S23)

> **NO VALIDADO en Android.** Todo se probó en un contenedor Linux. Termux es un entorno POSIX, de modo que
> se espera compatibilidad, pero no se ha comprobado; los resultados deben confirmarse en el teléfono.

## 1. Requisitos

- **Termux** con Python 3.11 o posterior, ya instalado por el usuario. Este proyecto no instala nada.
- **ZIP extraído en el almacenamiento PRIVADO de Termux** (por ejemplo `~/EquipoIA_V3`), no en
  `/sdcard`: el almacenamiento compartido no admite enlaces simbólicos ni permisos POSIX.

## 2. Verificación

```sh
cd ~/EquipoIA_V3/equipo_ia_v3
python3 -B verificar_v3.py              # F0–F9 (en el teléfono, varias veces más lento que en Linux)
python3 -B verificar_v3.py --completo   # además la línea base de 503 pruebas
```

- **Consumo.** Mantener el teléfono cargando y la pantalla activa (o `termux-wake-lock`) durante la ejecución
  completa, que es larga y usa la CPU de forma sostenida.
- **STOP.** El mecanismo de V2-F.1 se conserva: crear `$TMPDIR/equipo_f2/lab_v2f1/tareas/<LAB-NNN>/STOP` detiene la
  tarea. Las importaciones de V3 respetan además `<lab>/STOP`.

## 3. Modelo real (Qwen) en el teléfono

V2-F.1 está pensado para el teléfono: `qwen-coder-3b.gguf` bajo `$HOME`, contexto 1024 o 2048 y 4 hilos. Ver
`sistema/LEEME_V2F1.md` §3, donde se describe la demostración real con `--qwen-real --iniciar-servidor-real`, que
exige la autorización explícita del usuario.

- **El modelo no se incluye.** Ni el GGUF ni llama-server forman parte del paquete, y el proyecto no descarga
  nada.
- **Comprobaciones pendientes.** Las comprobaciones V-QWEN-01 a 05 figuran como NO VERIFICADAS en la línea base,
  porque requieren ese entorno.

## 4. Uso básico

```sh
cd sistema && python3 -B equipo.py demo funcion && cd ..
python3 -B equipo3.py traza importar LAB-001
python3 -B equipo3.py traza verificar LAB-001/E001
python3 -B equipo3.py memoria consultar A2 "revisar la mediana de una lista"
```

## 5. Lo que no se ha validado en Android

La ejecución de la suite en Termux, Qwen real, los tiempos, el consumo de memoria y batería y el comportamiento
del STOP con el modelo cargado.
