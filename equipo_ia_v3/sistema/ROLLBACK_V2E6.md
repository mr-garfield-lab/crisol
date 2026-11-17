# Rollback de V2-E.6

V2-E.6 **no reemplaza ni modifica** nada anterior:
- **Código:** vive en su propia carpeta, `$TMPDIR/equipo_f2/codigo_v2e6/equipo_f2_v2e6/`.
- **Datos:** viven solo en `$TMPDIR/equipo_f2/lab_v2e6/`. Incluye verificaciones, auditorías, aprendizaje, retos, pruebas variables y runs.
- **Lo que no toca:**
  - la carpeta de código de r3 ni sus datos (`datos_v2e5r3`; las pruebas lo comprueban);
  - `~/equipo-ia`;
  - el GGUF;
  - nada de Zomboid.

## Volver a V2-E.5-r3
Basta con seguir usando la carpeta de r3. No hay nada que deshacer:
```
cd "$TMPDIR/equipo_f2/codigo_v2e5r3/equipo_f2_v2e5r3"
python3 -B verificar.py
```
- r3 escribe sus verificaciones en `$TMPDIR/equipo_f2/verificacion/`.
- V2-E.6 escribe las suyas en `$TMPDIR/equipo_f2/lab_v2e6/verificacion/`.
- No se mezclan.

## Retirar V2-E.6 por completo (opcional; lo decides tú)
1. **Para la sesión en curso.** Si hay alguna en marcha, crea el archivo `STOP`:
   ```
   touch "$TMPDIR/equipo_f2/lab_v2e6/STOP"
   ```
   Después, comprueba que no queda ningún `llama-server` de V2-E.6:
   ```
   python3 -B supervisar.py estado
   ```
2. **Conserva lo que quieras guardar.** Por ejemplo, los informes para GPT-6:
   ```
   cp -r "$TMPDIR/equipo_f2/lab_v2e6/verificacion" ~/storage/downloads/verificacion_v2e6
   ```
3. **Borra las dos carpetas de V2-E.6.** Solo esas; ninguna es de otra versión:
   - `"$TMPDIR/equipo_f2/codigo_v2e6"`
   - `"$TMPDIR/equipo_f2/lab_v2e6"`

## Volver a un estado intermedio de V2-E.6
- **Aprendizaje:**
  - Las bases de aprendizaje se copian en `lab_v2e6/copias/` antes de cada sesión (`a1_apr_<run>.db`…).
  - Para recuperar una copia, para cualquier sesión y reemplaza el archivo de `lab_v2e6/aprendizaje/` por esa copia.
  - Un recuerdo verificado por error se revoca sin borrar nada:
    ```
    python3 -B aprender.py revocar --agente A1 RC-000001 --motivo "..." --autorizo --nombre "..."
    ```
- **Reanudación:** reanudar es explícito, con `--reanudar RUN_ID`. La ejecución anterior y sus evidencias no se modifican.
- **Paquetes autorizados:**
  - `lab_v2e6/auditoria/autorizados.json` es una lista de SHA-256.
  - Para retirar una autorización, edita ese archivo (es tuyo).
  - El historial queda en `registro.jsonl`.
