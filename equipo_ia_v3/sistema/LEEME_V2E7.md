> **Esta entrega es V2-E.7-r3** (auditoría A3 de las tareas `modlab_pz`, sobre V2-E.7-r2): lee también `LEEME_V2E7R2.md` y `LEEME_V2E7R3.md`. La carpeta de datos es `lab_v2e7r3`.

# Equipo IA — V2-E.7: equipo operativo con tareas LAB-NNN

Copia nueva de V2-E.6-r3. Las versiones anteriores y sus carpetas (`lab_v2e6r3`, `lab_v2e6r2`, `lab_v2e6`, `datos_v2e5r3`…) no se tocan. Los datos de esta versión van a `$TMPDIR/equipo_f2/lab_v2e7r3/`.

## Qué se reutilizó y qué es nuevo
- **Reutilizado:**
  - el motor de V2-E (`motor.py`: planificar → generar → revisar → probar → evaluar → corregir);
  - el backend real de Qwen (`backend_llama.py` + `servidor.py`, con sus comprobaciones de modelo, memoria, puerto, proceso `llama*` ya activo y STOP);
  - los proyectos versionados (`proyecto.py`);
  - el laboratorio confinado (`rutas.py`).
- **Nuevo en el motor (solo con `pruebas_por_a2=True`):**
  - A2 escribe las pruebas (estado `PRUEBAS`) y A1 ya no puede escribirlas ni tocarlas al corregir;
  - el resultado `criterios_verificados` solo se alcanza con pruebas reales;
  - A3 audita la evidencia **antes** de que se cierre llama-server.
- **Nuevo:** `ejecutor_restringido.py` + `corredor_pruebas.py` (ejecución real de las pruebas), `tareas.py` (guardado y exportación) y `equipo.py` (órdenes).

## Órdenes (Termux, una por mensaje)
1. `python3 -B equipo.py tarea importar ejemplos/tarea_demo.json`
2. `python3 -B equipo.py tarea ejecutar LAB-001 --autorizo-pruebas`
3. `python3 -B equipo.py tarea estado LAB-001`
4. `python3 -B equipo.py tarea exportar LAB-001` (o `ultima`)

Sobre la orden 4:
- Crea `…/lab_v2e7r3/exportaciones/EQUIPO_IA_LAB-001_ENTREGA.zip`. Si ese nombre ya existe, crea `_v2`, `_v3`, etc., y nunca sobrescribe.
- La orden imprime cómo copiarlo a Descargas.

Sobre la orden 2:
- Usa **Qwen real**: arranca llama-server con el GGUF, solo en lectura.
- **Sin `--autorizo-pruebas`** no se ejecuta ninguna prueba, y el resultado no puede ser «verificado».

Formato de la tarea:

```json
{"id": "LAB-001", "titulo": "…", "instrucciones": "… (máx. 600 caracteres)", "max_iteraciones": 2}
```

`id` es opcional; si falta, se asigna el siguiente libre. Un `id` repetido se rechaza, nunca se sobrescribe.

## Qué se guarda (en `tareas/<ID>/`, nada se sobrescribe ni se borra)
- **Tarea:** `tarea_original.json` (bytes tal cual), `tarea.json` (normalizada, con el SHA-256 del original) y `eventos.jsonl` (historial con hora).
- **Una carpeta por ejecución,** `ejecuciones/E<nnn>/`, con:
  - `runs/<run>/motor/eventos.jsonl` e `informe.json`: acciones de cada agente, estados, tiempos, llamadas y métricas;
  - `runs/<run>/proyecto/v<n>/`: cada versión del código, con su manifiesto;
  - `pruebas/P<nnn>/`: el espacio ejecutado, `registro.json` (comando, código de retorno, duración, nonce, huellas de entrada y salida, límites aplicados), `salida.txt`, `errores.txt` e `informe_unittest.txt`;
  - `auditoria/`: `determinista.json` (la conclusión del código), `A3_auditoria.txt` (el texto de A3) y `A3_evidencia_recibida.json`;
  - `MANIFIESTO_SHA256.txt`.
- **El ZIP de exportación** lleva todo lo anterior, un `LEEME.txt` y un `MANIFIESTO_SHA256.txt` que se comprueba con `sha256sum -c`.

## Quién decide «verificado»
El código, nunca un agente. Hace falta que se cumpla todo esto:
- el motor terminó en `criterios_verificados`;
- todos los criterios de A2 pasaron en una ejecución **real**;
- la última ejecución fue `ok`, con el nonce correcto;
- los archivos coinciden con su manifiesto.

El veredicto de A3 (`conforme` / `no_conforme`) se guarda aparte y no cambia esa conclusión.

## Seguridad del ejecutor (y su límite)
Termux sin root no tiene sandbox, y el Modo B sigue deshabilitado (`MODO_B_HABILITADO = False`). El ejecutor restringido es la capacidad mínima, organizada en capas:

1. **Lista blanca AST antes de ejecutar nada.** Solo se permiten módulos de cálculo de la biblioteca estándar y los propios del proyecto. Quedan fuera `open`, `exec`, `eval`, `getattr`…, los atributos privados o dunder, los atributos con nombre de módulo peligroso (`os`, `sys`…) y las reasignaciones de atributos ajenos.
2. **Proceso hijo `python3 -I -S -B`** sobre una copia del espacio, con entorno mínimo y límites del núcleo: CPU, memoria, tamaño de archivo, descriptores y ningún proceso nuevo.
3. **Gancho de auditoría** que bloquea escribir fuera del espacio, leer fuera del espacio y de la biblioteca estándar, red, subprocesos, señales, `ctypes` e inspección de marcos.
4. **Tiempo límite.** Solo se termina al propio hijo.
5. **Nonce.** Los resultados sin el nonce de la ejecución no cuentan.

**No es un aislamiento del sistema operativo.** Es defensa en capas sobre código de cálculo puro.

## Qué está probado y qué no
- **Probado (sandbox Linux):**
  - la demostración de extremo a extremo: A1 crea `ordenar.py` con un error, A2 escribe la prueba, la ejecución real falla, A1 corrige, la ejecución real pasa, A3 audita, y se exporta y verifica el ZIP;
  - los ataques bloqueados por la lista blanca y por el gancho;
  - el resultado falsificado y el bucle infinito;
  - la ruta HTTP completa con el servidor FALSO.
- **No probado:** Qwen real, Termux real y Windows. En la demostración los textos de los agentes son un guion.
- La recuperación tras SIGKILL de la propuesta r4 **no está implementada**. Rige el bloqueo de r3: si hay cualquier proceso `llama*` o el puerto está ocupado, no se arranca nada.
