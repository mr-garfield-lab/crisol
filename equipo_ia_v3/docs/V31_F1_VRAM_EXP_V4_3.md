# V3.1 F1-VRAM-EXP-V4.3 — control de fugas del oráculo con procedencia

**Estado:** laboratorio experimental, prerregistrado. La evaluación F1 completa **no** se ha vuelto a ejecutar.

## 1. Diagnóstico (F1 con V4.2, 2026-11-12, 11:29–11:45)

- La evaluación abortó en `r1/E3/T10`, paso 2, con `FugaDeOraculo ['T10.esperado']` (aborto ordenado, código 3).
  Detalle en `evidencias/v31_f1_vram_exp_v4/f1_comparacion1/aborto.json`.
- **Qué pasó:**
  - A1 (Qwen) escribió por sí mismo la respuesta correcta, `return ['a', 'b', 'c']`
    (SHA-256 de su salida `209f07e7…cce`).
  - El controlador de E3 (V2-F.1) la pasa a A2 en el bloque `DATOS_NO_CONFIABLES fuente=codigo`.
  - `evaluacion_f1.fugas_de_oraculo` busca el literal esperado en **todo** el prompt, sin distinguir de dónde viene,
    y aborta.
  - Es un **falso positivo**: el texto lo produjo el modelo, no venía del oráculo.
- **Por qué no se vio antes:**
  - G10 usaba el servidor falso de V2-F.1, que nunca acierta.
  - S1 y S1×3 no pueden fallar así: hacen una sola petición y ningún prompt lleva texto del modelo.
  - Solo E3 retransmite texto de un agente a otro.
- **Defecto secundario:** `FugaDeOraculo` deriva de `BaseException`. No la atrapa `ejecutar_bucle`, así que
  `comparacion.json` quedó sin `abortada` ni `valida`; el motivo solo salió por pantalla.

## 2. Corrección (solo en el laboratorio)

V4.3 es un archivo NUEVO, `eq3/evaluar_f1_vram_exp_v4_3.py`: una copia de V4.2 con los cambios de abajo. Siguen
intactos:
- `eq3/evaluar_f1_vram_exp_v4.py` (V4.2);
- la estable (`evaluar_f1.py`, `evaluacion_f1.py`) y V2-F.1 (`sistema/`);
- los prerregistros V1–V4.2;
- las evidencias de las 39 ejecuciones.

### 2.1 Procedencia del texto (`fugas_con_procedencia`)

Distingue tres orígenes:
- **Oráculo**: lo que busca la estable, con los mismos textos y umbrales (`textos_oraculo`, que la reproduce y se
  prueba contra ella).
- **Evaluador y controlador**: las cabeceras SISTEMA/USUARIO y los bloques `tarea`, `casos_usuario`, `orden_trabajo`,
  `experiencias` y cualquier fuente desconocida.
- **Agentes**: las respuestas que el servidor de ESTA tarea devolvió de verdad. `proteger_backend_v43` las guarda, con
  su SHA-256, al salir de `completar`.

Una aparición de un texto del oráculo deja de ser fuga **solo si se cumple todo**:
1. La configuración es **E3**. En S1 y S1×3 nunca se exime nada: el resultado es idéntico al de la estable.
2. La aparición está dentro de un **bloque de relevo**: `codigo`, `evidencia`, `pendientes`, `respuesta_a1`,
   `mejoras_a2`, `casos_previos`, `problemas`, `intentos`, `casos` o `sugerencias`. Los delimitadores no se pueden
   falsificar: `sanea` neutraliza `<<<` y `>>>` en el texto de los agentes.
3. La línea que la contiene es **copia literal** de una respuesta anterior de ESTE servidor en ESTA tarea:
   - se comparan ambos lados normalizados como lo hace `sanea` (NFC, sin controles, espacios colapsados);
   - se quita el número de línea `  2| ` que añade el controlador;
   - hace falta la línea entera, o el literal más al menos **12 caracteres** de contexto copiado (`CONTEXTO_MIN`).
   
   Que la cadena aparezca en una respuesta **no basta**: el contexto tiene que coincidir.
4. **Ningún prompt anterior expuso el oráculo.** Tras una fuga no se exime nada más (`expuesto`). Además, cada
   prompt se comprueba antes de enviarse, así que una respuesta solo puede contener un texto del oráculo si el modelo
   lo produjo sin haberlo visto.
5. **Todas** las apariciones de esa etiqueta cumplen 1–4. Basta una sin verificar para que sea fuga, y ante cualquier
   duda también lo es (fallo cerrado).

Cada relevo eximido queda anotado en `metricas.peticiones[n].relevos_verificados`, con su etiqueta, fuente, número y
SHA-256 de la respuesta de origen y longitud del contexto copiado.

### 2.2 Cómo se integra

- `ejecutar_tarea_e2` llama a `EV.ejecutar_tarea` dentro de `_protector_v43(configuracion)`.
- Eso sustituye `EV.proteger_backend` **solo en este proceso y solo durante esa tarea**, y lo restaura siempre
  (también ante una excepción). El archivo de la estable no cambia.

### 2.3 Fuga anotada

`comparar` captura `FugaDeOraculo` y, antes de volver a lanzarla, guarda en `comparacion.json`:
- `abortada: "fuga_del_oraculo: …"`;
- `valida: false`;
- el registro del fondo animado.

`fondo_gestionado` sigue restaurando Wallpaper Engine.

### 2.4 Sin cambios

- E2 (`--fit off -ngl all -fa on -ub 128 -b 512`);
- límites: 6912 MiB de VRAM total y 1992 MiB de VRAM ajena;
- control de persona y recursos, STOP, RAM, propiedad de procesos y guardián del fondo;
- tareas, oráculos, prompts, orden, temperaturas, semillas, contexto, iteraciones y regla de decisión.

## 3. Pruebas

| Grupo | Qué prueba | Archivo |
|---|---|---|
| Regresión de V4.2 | Las 17 pruebas de V4.2, sobre el módulo V4.3 | `pruebas/test_eq3_evaluar_f1_vram_exp_v4_3.py` |
| Equivalencia | Sin respuestas = exactamente la estable (todas las configuraciones); textos y etiquetas iguales a los de la estable; S1/S1×3 nunca eximen | `pruebas/test_eq3_procedencia_v4_3.py` |
| **A1 acierta y A2 lo recibe** | Unitario, con el código numerado y sin numerar. Integración con el flujo real de V2-F.1: E3/T10 llega a CORRECTO y el relevo está ligado al SHA-256 de A1 | ídem |
| **El oráculo aparece de verdad** | En `tarea`, `orden_trabajo`, `casos_usuario`, `experiencias`, una fuente desconocida o la cabecera: fuga. En integración aborta en S1, S1×3 y E3 sin enviar nada | ídem |
| **Coincidencia** | Literal en otro contexto (evidencia o problemas que no copian una respuesta): fuga. Frase de A2 retransmitida con el formato del controlador: relevo verificado | ídem |
| **Contenido contaminado** | Relevo que el modelo no escribió, sin respuestas o con respuestas parecidas: fuga. Tras una exposición no se exime nada. Otra tarea no hereda respuestas. Si el texto ya estaba en el prompt de A1, aborta en los tres métodos antes de cualquier relevo | ídem |
| Delimitadores falsos | Un bloque `codigo` falsificado dentro de `tarea` sigue contando como `tarea` | ídem |
| Cableado | `ejecutar_tarea_e2` usa el protector nuevo; el protector se restaura; `comparar` anota la fuga y restaura el fondo; G10 exige estas pruebas | ídem |
| Mutaciones F23 | 36 mutaciones: las 22 de V4.2, reaplicadas al módulo V4.3, y 14 del detector y su cableado | `v3/mutaciones/v31_f1_vram_exp_v4_3.json` |
| Repetición sin modelo | Los 45 prompts reales de E3 guardados en la F1 abortada dan los mismos resultados con la estable y con V4.3 (0 fugas, 0 relevos). T10, con la salida real de A1: la estable aborta tras 1 prompt; V4.3 envía 3 y acaba en CORRECTO | `lab_vram/repetir_prompts_f1_v4_3.py` → `evidencias/v31_f1_vram_exp_v4_3/repeticion_sin_modelo/` |

Resultado de las puertas: `docs/V31_F1_VRAM_EXP_V4_3_PUERTAS.md`.

## 4. Riesgo residual

- **Una exención nueva y acotada.** Si Qwen escribe por sí mismo un texto del oráculo y E3 lo retransmite, ya no
  aborta. Es el comportamiento buscado: el modelo no lo vio antes, porque cada prompt se comprueba antes de enviarse.
- **El conjunto `FUENTES_RELEVO` está fijado a V2-F.1.** Si V2-F.1 añadiera un bloque nuevo, contaría como fuente
  desconocida y sería fuga, es decir, fallo cerrado. Nunca relajaría el control.
- **Un falso positivo similar sigue siendo posible**, por ejemplo si el controlador citara el literal con su propio
  formato y menos de 12 caracteres copiados. En ese caso aborta (fallo cerrado), no se pierde ninguna protección.
- **La procedencia se basa en el texto devuelto por `completar`.** Un cambio de V2-F.1 que reescribiera mucho las
  respuestas antes de retransmitirlas haría que más relevos se trataran como fuga: de nuevo, fallo cerrado.
