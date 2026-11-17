# Equipo IA V3 — Etapa 8: paquete final

**Estado: CERRADA** (2026-11-10). El ZIP extraído en limpio pasa el verificador completo: 12 fases (F0–F11) correctas.

## 1. Qué se entrega

| Elemento | Dónde |
|---|---|
| ZIP autocontenido | `dist/equipo_ia_v3_<commit>/EquipoIA_V3.zip` (fuera de Git: `dist/` está en `.gitignore`) |
| SHA-256 del ZIP | `EquipoIA_V3.zip.sha256`, junto al ZIP |
| Manifiesto de cada archivo | `EquipoIA_V3/MANIFIESTO_SHA256.json`, dentro del ZIP |
| Código fuente, configuración y dependencias | `equipo_ia_v3/` (solo la biblioteca estándar de Python 3.11 o posterior, sin dependencias externas) y `fuentes/` (las selecciones originales que la línea base necesita) |
| Orden única de pruebas | `python3 -B verificar_v3.py --completo` (F0–F11) |
| Informes por etapa | `docs/ETAPA0_AUDITORIA.md` … `docs/ETAPA8_PAQUETE.md` |
| Registros y evidencias | `evidencias/` (cada carpeta con su `LEEME.md`) |
| Comparación antes y después | Línea base de V2-F.1 (503 pruebas, IGUAL) frente a las capacidades añadidas (`docs/INVENTARIO_FUNCIONES.md`) |
| Inventario de funciones y su naturaleza | `docs/INVENTARIO_FUNCIONES.md` |
| Limitaciones | En cada informe, en `PROGRESO.md` y en el §4 de este documento |
| Guías de Windows y de Android/Termux | `docs/GUIA_WINDOWS.md`, `docs/GUIA_TERMUX.md` |
| Recomendaciones | §5 |

**Qué NO contiene**, comprobado por `v3/empaquetar.py`, que rechaza el paquete si lo encuentra:

- GameAgentEngine;
- bases SQLite, modelos GGUF, cachés o ZIP anidados;
- enlaces simbólicos;
- credenciales o direcciones de correo. La única excepción es una fixture sintética de Contexto Ligero, ligada a su
  SHA-256.

## 2. Verificación del paquete

1. **ZIP de `5ca1c5a`.** Tiene 620 entradas (2,4 MB) y SHA-256 `669675d3ddcf0fbb232ca26f791a53b5c2161cee46691ed4ac873249bf866ae1`.
   Se extrajo con `extraer_seguro` en una carpeta NUEVA fuera del repositorio, y los 618 archivos coinciden con el
   manifiesto.
2. **`verificar_v3.py --completo` desde la copia extraída:** 12 de 12 fases correctas en 757 s. Las mutaciones dan 9/9, 12/12, 6/6, 12/12, 10/10, 9/9, 9/9 y 7/7, y la línea base IGUAL 503 de 503 (`evidencias/etapa8/`).
3. **ZIP final:** se reconstruye después del commit de cierre para incluir este documento. Solo cambian la documentación, las evidencias y `PROGRESO.md`, lo que se comprueba comparando los dos manifiestos, y se vuelve a pasar el verificador rápido sobre el ZIP final extraído.

## 3. Resumen del estado final

Etapas 0–8 terminadas. Cada una tiene pruebas, mutaciones y una fase en el verificador integral:

- 95 pruebas propias (funciones `test_*` de `pruebas/` y `v3/tests/`);
- 74 mutaciones, todas detectadas;
- la línea base de V2-F.1 da IGUAL 503 de 503.

## 4. Limitaciones principales (no se declaran resueltas)

1. **Sin modelos reales.** Ninguna función se ha verificado con Qwen real: los agentes de todas las ejecuciones
   están SIMULADOS.
2. **Sin plataformas reales.** No hay validación en Android/Termux ni en Windows 11. En Windows, las pruebas que
   crean enlaces simbólicos requieren el Modo de desarrollador.
3. **SEG-01 abierto.** No hay aislamiento del sistema operativo, así que no se ejecuta el código generado: el
   resultado es «aceptado sin ejecución», nunca «verificado».
4. **Material omitido.** 25 comprobaciones de V2-F.1, 1 de codex y 5 de Contexto Ligero dependen de él. Hacen
   falta los ZIP originales.
5. **Estimaciones.** Las cifras del PC son estimaciones. La memoria es léxica y los escenarios son propios, aunque
   prerregistrados.

## 5. Recomendaciones (siguientes pasos, con autorización del usuario)

1. **Validar en el teléfono.** Ejecutar `verificar_v3.py --completo` en Termux; luego, la demostración real de
   V2-F.1 con Qwen (`--qwen-real`), e importar su traza en V3.
2. **Validar en el PC.** Ejecutar la suite en Windows y lanzar llama-server con la orden de `pc planificar`.
   Medir la VRAM y los tokens por segundo reales y comparar con la Etapa 6.
3. **Restaurar el material omitido.** Con los ZIP originales, actualizar la línea base explicando cada MEJORA.
4. **Abordar SEG-01.** Solo con aislamiento real (contenedor o usuario separado en el PC): ejecutar las pruebas
   generadas bajo autorización.
5. **Integrar el contexto y la memoria en los prompts de A1/A2/A3.** Requiere tocar `sistema/` con una línea base
   nueva; medir con Qwen si mejoran las respuestas.
