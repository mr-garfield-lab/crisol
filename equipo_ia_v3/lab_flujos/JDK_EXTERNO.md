# JDK externo (Java) para el banco de revisión de código

Instalado el 2026-11-15 a petición del usuario, en modo portátil: sin instalador, sin permisos de administrador y sin
tocar el PATH ni el registro de Windows. Está FUERA del proyecto y no va en ningún ZIP.

| | |
|---|---|
| Producto | Eclipse Temurin JDK 21 (LTS), Windows x64, HotSpot |
| Versión | 21.0.13+9 |
| Archivo | `OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.zip` (205 421 281 bytes, 195,9 MB) |
| Origen | https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.zip |
| Publicado | 2026-10-29, por Eclipse Adoptium |
| SHA-256 publicado (API de Adoptium) | `a4dbaa05fca4bd89d84584e58c459bd732efebb1722af80ab13c6516832004f9` |
| SHA-256 calculado | idéntico (comprobado antes de abrir el archivo) |
| Zip descargado | `externos/descargas/jdk21_temurin/` |
| JDK extraído | `externos/jdk_temurin_21/jdk-21.0.13+9/` (compilador: `bin/javac.exe`) |

## Comprobado
- `javac 21.0.13` y `java` (Temurin-21.0.13+9) arrancan.
- Un archivo correcto compila con código 0. Con errores, `javac` da el archivo, la **línea exacta**, el tipo de error y
  el símbolo (`cannot find symbol`, `incompatible types: int cannot be converted to String`, `';' expected`).

## Dos detalles que importan para el banco
1. **`javac` rechaza los archivos con BOM** (`illegal character: '﻿'`). El `Set-Content -Encoding UTF8` de
   PowerShell 5.1 lo añade. Los archivos Java del banco se escriben SIEMPRE en UTF-8 sin BOM y se compila con
   `-encoding UTF-8`.
2. **`javac` informa por fases.** Si hay un error de sintaxis, solo muestra ese: los errores de tipos o de nombres
   inexistentes aparecen cuando la sintaxis ya está bien. Un archivo con los dos tipos de fallo da una respuesta
   distinta antes y después de corregir el primero; el banco lo tiene en cuenta (oráculo por fase).

## Si hay que quitarlo
Borrar `externos/jdk_temurin_21/` y `externos/descargas/jdk21_temurin/`. No hay nada más que deshacer.
