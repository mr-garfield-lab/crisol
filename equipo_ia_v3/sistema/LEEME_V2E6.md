> **Esta entrega es V2-E.7** (equipo operativo, tareas LAB-NNN): lee primero `LEEME_V2E7.md`. Lo que sigue describe V2-E.6 y sigue valiendo, con la carpeta de datos `lab_v2e7`.
> **Esta entrega es V2-E.6-r3** (corrección del hallazgo C de la auditoría GPT-6): lee primero `LEEME_V2E6R3.md` y después `LEEME_V2E6R2.md`. Todo lo de este documento sigue valiendo, con la carpeta de datos `lab_v2e6r3` en lugar de `lab_v2e6` y el ZIP `equipo_f2_v2e6r3.zip`.

# Equipo IA — V2-E.6

Versión nueva y **separada**, construida sobre la copia auténtica de V2-E.5-r3 (su manifiesto coincide byte a byte con el de la entrega r3; está en `herramientas/manifiesto_r3.txt`).

**Garantías de esta versión:**
- **No se modifica la r3 ni sus datos.** V2-E.6 escribe solo en `$TMPDIR/equipo_f2/lab_v2e6/`.
- **No se toca nada del usuario:** ni `~/equipo-ia`, ni el GGUF (solo lectura y solo con Qwen real autorizado), ni partidas o archivos de Zomboid. No hay red.
- **Configuración segura:**
  - `MODO_B_HABILITADO = False`;
  - 4 hilos y `NP=1` (un solo Qwen secuencial);
  - personalidad desactivada por defecto.
- **No se ejecuta código generado por los agentes, ni código de paquetes, ni `generar_reto.py`.**
- **Sin dependencias nuevas.** Solo la biblioteca estándar de Python ≥ 3.11. La instalación usa `python3 -m zipfile`, así que no hace falta `unzip`.
- **Todo lo probado aquí es SIMULADO o de servidor FALSO, en una sandbox Linux.** Nada se ha ejecutado en Termux, en Windows ni con Qwen real (ver §5).

## 1. Instalación aislada en Termux

### En un solo comando
Ajusta la ruta del ZIP si lo guardaste en otro sitio:
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e6" && cd "$TMPDIR/equipo_f2/codigo_v2e6" && python3 -m zipfile -e ~/storage/downloads/equipo_f2_v2e6.zip . && cd equipo_f2_v2e6 && python3 -B verificar.py
```

### Paso a paso (un comando por mensaje)
1. `mkdir -p "$TMPDIR/equipo_f2/codigo_v2e6"`
2. `cd "$TMPDIR/equipo_f2/codigo_v2e6"`
3. `sha256sum ~/storage/downloads/equipo_f2_v2e6.zip`
   - Compara el resultado con el SHA-256 del ZIP que figura en la entrega.
4. `python3 -m zipfile -e ~/storage/downloads/equipo_f2_v2e6.zip .`
5. `cd equipo_f2_v2e6`
6. `sha256sum -c --quiet MANIFIESTO_SHA256.txt && echo INTEGRO`
   - Es opcional: `verificar.py` también comprueba las huellas (V-INT-01).
7. `python3 -B verificar.py`
   - Es la batería completa.
   - Salida 0: sin fallos. Salida 1: hay fallos (ver `trazas/`). Salida 2: no se pudo preparar.

Si `~/storage/downloads` no existe, ejecuta antes `termux-setup-storage`, o usa la ruta en la que guardaste el ZIP.

## 2. La orden única de verificación
`python3 -B verificar.py` ejecuta todo lo seguro que hay disponible, en 21 fases.

**Qué se ve en pantalla:**
- Cada fase va entre `===== INICIO FASE n/N · …` y `===== FIN FASE …`.
- Cada comprobación lleva su resultado y su **naturaleza**:
  - **REAL** comprueba el árbol o la plataforma reales;
  - **SIMULADA** usa backend simulado, servidor FALSO o datos sintéticos;
  - **OMITIDA** o **NO VERIFICADA** indican, con el motivo, que no se ejecutó.

**Qué se guarda** en `$TMPDIR/equipo_f2/lab_v2e6/verificacion/<id>/`:
- `informe.json` e `informe.md`;
- `terminal.log`, con todo lo mostrado;
- `eventos.jsonl`, con CPU y RAM medidas cuando la plataforma lo permite;
- `trazas/`;
- `cumplimiento_resultado.md`;
- `diff_r3.json`;
- `pruebas_variables.md`;
- `demos/`.

| Orden | Qué hace |
|---|---|
| `python3 -B verificar.py --rapido` | Batería sin repeticiones. |
| `python3 -B verificar.py --semilla 7` | Añade una semilla a las fijas (11, 42, 2026). |
| `python3 -B verificar.py --demo` | Solo las demostraciones. |
| `python3 -B verificar.py --lista-demos` | Muestra las órdenes de cada demostración, para ejecutarlas a mano. |
| `python3 -B verificar.py --lista` | Catálogo por fases, sin ejecutar nada. |
| `python3 -B verificar.py --solo V-ZOM --solo V-APR` | Solo las comprobaciones de esas fases. |
| `python3 -B verificar.py --qwen-real --iniciar-servidor-real` | Añade la fase **QWEN** con el modelo real. Es la única forma de usarlo y exige ambas banderas. |

Detalles en `VERIFICADOR.md`.

## 3. Qué hay de nuevo, por área
| Área | Dónde | Cómo probarlo |
|---|---|---|
| 1. Contexto y tokens | `src/eq2/perfiles_contexto.py`: perfiles seguro 1024, referencia 2048 (= r3), ampliado 2560 y experimental 3072; límites estrictos por tarea y sesión; retroceso por RAM o servidor | `python3 -B ejecutar_v2.py --modo deliberacion --perfil-contexto ampliado --iniciar-servidor-real` (real) · fase CTX |
| 2. Laboratorios | `laboratorios.py` (esquema 3): artefactos con SHA-256 y versiones, evidencia con fuente y líneas comprobadas, hipótesis falsables, comprobaciones declarativas, pendientes del coordinador | fase LAB · `retos.py tuberia --caso fuentes` |
| 3. Agentes | `roles.py`: tarjetas de rol persistentes; `independencia.py`: eco de la propuesta, autoridad del autor, aprobación sin comprobación, votos similares, autovoto | fase AGT |
| 4. Aprendizaje | `aprendizaje.py` y `aprender.py`: estados, evidencias, recuperación con metadatos, feedback humano autorizado; `evaluacion_aprendizaje.py`: pre/post SIMULADO | `python3 -B aprender.py evaluar` · `aprender.py auditar` |
| 5. Pruebas variables | `pruebas_variables.py`: semillas, niveles 1–3, perturbaciones, adversarios, oráculos ocultos | `python3 -B retos.py variables --semilla 7` |
| 6. Zomboid | `retos/zomboid_v1/` (material original íntegro + datos propios) y `retos.py` (generador seguro, puntuador 0–12, tubería A2→A1→A3) | `python3 -B retos.py referencias` · `python3 -B ejecutar_v2.py --modo reto_simulado` |
| 7. Paquetes | formato `eq2/desafio` v1 en `paquetes_auditoria.py`; ejemplo `retos/zomboid_v1/paquete_desafio/` | fase CON (V-CON-03) |
| 8. Calidad | STOP en continuación y limpieza; reanudación EXPLÍCITA (`ejecutar_v2.py --modo deliberacion --reanudar RUN_ID`); tareas registradas por ejecución | fase STOP |
| Verificación | `verificar.py` por fases, con naturaleza, registros, eventos, métricas, semillas, demostraciones, cumplimiento y diferencias con r3 | `python3 -B verificar.py` |

La lista completa de cambios frente a r3 está en `CAMBIOS_V2E6.md`. La tabla requisito → archivo → prueba → resultado está en `CUMPLIMIENTO_V2E6.md`.

## 4. Uso con Qwen real (solo con tu autorización)
Exige el binario `llama-server` y el GGUF original, que se lee en solo lectura. Nada arranca sin `--iniciar-servidor-real`.

| Orden | Qué hace |
|---|---|
| `python3 -B ejecutar_v2.py --modo comprobar` | Comprobaciones previas. No arranca el servidor. |
| `python3 -B ejecutar_v2.py --modo reto --iniciar-servidor-real --max-casos 1` | Reto Zomboid: 3 llamadas. |
| `python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real` | Deliberación con el perfil de referencia (2048). |
| `python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real --perfil-contexto ampliado` | Deliberación con 2560, si hay RAM suficiente; si no, retrocede y lo dice. |

STOP: crea el archivo `$TMPDIR/equipo_f2/lab_v2e6/STOP`. Para reanudar después lo que quedó a medias, usa `--reanudar RUN_ID`.

## 5. Lo que NO se ha probado
- **Termux, Windows y Qwen real:** no hay dispositivo, ni GGUF, ni `llama-server` en la sandbox.
- **Perfiles 2560 y 3072:** no se midieron con Qwen. Los umbrales de RAM son estimaciones conservadoras.
- **Aprendizaje de Qwen:** la evaluación pre/post demuestra el **mecanismo** con una política determinista, no que Qwen aprenda.
- **Puntuador Zomboid:** es heurístico. Mide la forma verificable de una respuesta (citas, matices, separación), no si el diagnóstico es cierto en el juego.

Más detalle en `LIMITES_Y_RIESGOS_V2E6.md`.

## 6. Rollback
V2-E.6 no reemplaza nada: volver a r3 es simplemente seguir usando su carpeta. Ver `ROLLBACK_V2E6.md`.
