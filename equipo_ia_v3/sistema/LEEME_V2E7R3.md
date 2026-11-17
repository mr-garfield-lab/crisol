# Equipo IA — V2-E.7-r3: evidencia verificada para la auditoría de A3 (modlab_pz)

**Estado: NO estable.** Pendiente de la revisión independiente (GPT-6) y de las pruebas reales en Termux (S23, Qwen 3B). No sustituye a V2-E.7-r2, que sigue siendo la versión estable. Datos en `$TMPDIR/equipo_f2/lab_v2e7r3/`; `lab_v2e7r2` y las anteriores quedan protegidas.

## El problema (ejecuciones reales de r2 en Termux)
En r2, A3 recibía solo la conclusión, el esperado, el obtenido y una línea por herramienta. No veía los pasos ni el inventario final. En LAB-003, A3 dijo `no_conforme` afirmando que el simulador no había rechazado el consumo imposible, cuando sí lo había rechazado.

## Qué cambia (solo la auditoría de A3 en tareas `modlab_pz`)
- **Nuevo `src/eq2/evidencia_pz.py`.** Construye la evidencia **releyendo del disco** los registros del coordinador, nunca el texto de A1/A2:
  - `herramientas/H<nnn>/registro.json`: operación, archivo, estado y huellas;
  - `herramientas/H<nnn>/resultado.json`: su SHA-256 se comprueba contra el registro;
  - `escenario/<archivo>`: su SHA-256 se comprueba contra el registro.
- **A3 recibe, en este orden:**
  1. objetivo de la misión;
  2. advertencia: «ModLab es una simulación declarativa propia; NO es Project Zomboid»;
  3. `resultado_esperado`;
  4. conclusión del evaluador determinista;
  5. operaciones solicitadas y ejecutadas;
  6. si la evidencia es suficiente, y las contradicciones;
  7. por operación: estado y categoría; por paso: acción, objeto, cantidad y `ok` o «RECHAZADO por el simulador»; el inventario final, los eventos y `todos_ok`.

  Lo esencial va primero: con `CTX=1024` también llega entero (probado con el motor real y el backend simulado).
- **Cuatro categorías**, por paso y por operación:

  | Categoría | Cuándo se asigna |
  |---|---|
  | 1. `simulada_exitosa` | El paso salió `ok`. |
  | 2. `fallo_esperado` | El paso fue rechazado y la tarea espera `fallo_detectado`. |
  | 3. `fallo_inesperado` | El paso fue rechazado sin esperarlo, o la herramienta dio error. |
  | 4. `sin_evidencia` | Herramienta no autorizada, rechazada por contrato o con archivo desconocido; registro ausente; huellas que no coinciden; o resultados contradictorios (pasos, `todos_ok` y registro no concuerdan). |
- **Instrucción `pz_auditar` de A3** (`motor.py`):
  - veredicto `conforme`, `no_conforme` (citando un paso o una contradicción concreta) o `evidencia_insuficiente`;
  - no se le obliga a decir `conforme`.

  Se guarda `cita_pasos: True/False` para ver si A3 justificó su veredicto.
- **Se guarda, además, en `auditoria/`:**
  - `A3_evidencia_recibida.txt`: el texto exacto que recibió A3;
  - `evidencia_verificada.json`: lo mismo, estructurado.
- **Sin cambios** en `determinista.json`, en su lógica, en el adaptador, en `modlab_pz/` ni en la seguridad (permisos, `--autorizo-pruebas`, STOP, bloqueo, RAM). La clasificación es informativa para A3.

## Pruebas (`tests/test_v2e7r3_auditoria_pz.py`, 8)
- LAB-001, LAB-002 y LAB-003 (con las instrucciones explícitas, y A3 discrepando sin citar pasos).
- Sin solicitudes y sin autorización; herramientas rechazadas; error del laboratorio.
- Resultados contradictorios; evidencia alterada en disco.
- Conclusión determinista idéntica con A3 `conforme` y `no_conforme`.
- La evidencia cabe en el prompt real de A3 con CTX 1024 y 2048.

## Límites
- Los escenarios LAB-001/002/003 están **recreados** a partir de la descripción. Los ZIP originales no se usaron ni se tocaron.
- Los textos de A1/A2/A3 en las pruebas son un **guion**, no Qwen. Que Qwen 3B use bien la nueva evidencia **no está probado**: queda pendiente la validación en el S23.

## Verificación
`python3 -B verificar.py` (imprime INICIO y FIN).
