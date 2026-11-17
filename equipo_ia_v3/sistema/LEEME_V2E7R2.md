> **Esta entrega es V2-E.7-r3** (no estable, pendiente de revisión): cambia solo la evidencia que recibe A3 en las tareas `modlab_pz`; lee `LEEME_V2E7R3.md`. En r3 los datos van a `lab_v2e7r3`, y `lab_v2e7r2` queda protegida.

# Equipo IA — V2-E.7-r2: integración de PZ ModLab 0.2

Copia nueva de V2-E.7 con `modlab_pz/` (de GPT-6), incluido **sin modificar**. V2-E.7 y las anteriores no se tocan. Datos en `$TMPDIR/equipo_f2/lab_v2e7r2/`.

## Qué cambia (mínimo)
- **Tareas `"tipo": "modlab_pz"`** en el mismo `equipo.py tarea importar | ejecutar | estado | exportar`:
  - **A1** prepara `escenario.json` (paso `pz_escenario`).
  - **A2** solicita las pruebas con líneas `SOLICITO: <operacion> <archivo>` (paso `pz_solicitar`).
  - **La herramienta** se ejecuta solo si la operación está en `modlab_pz/contrato_agentes.json`, el archivo es de la tarea y el usuario pasó `--autorizo-pruebas`.
  - **A3** audita un resumen en solo lectura.
- **Adaptador** `src/eq2/modlab_pz_adaptador.py`: llama solo a `simulate`, `inspect_zip` y `analizar_lua`. **No** usa `comprobar_sintaxis_archivo` (que lanza `luac`) ni `laboratorio.main`, y no ejecuta Lua ni Java.
- **Conclusión del código:**
  - `esperado_confirmado` si las simulaciones ejecutadas dan el `resultado_esperado` de la tarea (`todos_ok` o `fallo_detectado`);
  - `no_confirmado` si no lo dan;
  - `sin_pruebas` si no se ejecutó ninguna simulación.

  Un error de la herramienta no cuenta como «fallo detectado».
- **Guardado** en la ejecución:
  - `agentes/A1_escenario.txt` y `agentes/A2_solicitudes.txt`;
  - `escenario/`;
  - `herramientas/H<nnn>/{registro.json, resultado.json}`;
  - `auditoria/{determinista.json, A3_auditoria.txt}`;
  - `eventos.jsonl` y `MANIFIESTO_SHA256.txt`.

  Se exporta con el comando de siempre.

## Demostración con el escenario de fallo intencional (Termux, una orden por mensaje)
1. `python3 -B equipo.py tarea importar ejemplos/tarea_pz_fallo_intencional.json`
2. `python3 -B equipo.py tarea ejecutar LAB-001 --autorizo-pruebas` (usa el id que imprima el paso 1)
3. `python3 -B equipo.py tarea exportar ultima`

## Límites
- **No es un emulador:** es la máquina de estados propia de ModLab. No certifica compatibilidad con Project Zomboid ni con Build 42.
- **Qwen real no se ejecutó en esta entrega:** el sandbox no tiene GGUF ni llama-server. Ver el informe de entrega.
- **`modlab_pz/` queda fuera del validador estático del núcleo:** escribe sin `rutas.py` cuando se usa por su propia CLI. El equipo solo llama a sus funciones puras.
