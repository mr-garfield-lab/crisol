# Equipo IA — V2-E.2 (incidencias, causa raíz, contexto, laboratorio y auditoría) — ENTREGA PARA AUDITORÍA

Versión independiente construida sobre V2-E.1. **V2-E.1 y las versiones anteriores no se han modificado.** Las huellas SHA-256 de sus archivos coinciden con las de la entrega anterior.
**No se ha ejecutado el modelo real ni nada en Termux con este código.** La ejecución real de código generado y el Modo B siguen **deshabilitados**. Todos los resultados de este documento proceden de la sandbox Linux.

## 0. Etapas (se entrega solo la Etapa 1)
Para no arriesgar la estabilidad, todo lo nuevo es **independiente y opcional**: sin registro, el motor se comporta exactamente como en V2-E.1, y lo comprueba una prueba.
| Etapa | Contenido | Estado |
|---|---|---|
| **1 (esta entrega)** | Registro persistente con invariantes en la base, prioridad causal explicable, planificador con reasignación y límites, paquetes de contexto, laboratorio (estático, simulado y motor simulado), auditoría, interfaces futuras, enlace opcional con el motor y CLI `auditar.py` | Implementado y probado en la sandbox |
| 2 | Que el planificador **dirija** el bucle de corrección del motor con el modelo real (paquetes como entrada de A1/A2/A3) | No implementado |
| 3 | Complementos reales de otros lenguajes, interfaz gráfica, Windows 11, distribución | Solo interfaces |

## 1. Registro persistente de incidencias (`src/eq2/incidencias.py`)
- **Ubicación:** `$TMPDIR/equipo_f2/datos_v2e2/incidencias/incidencias.db` es la fuente de verdad. Junto a ella están las subcarpetas `evidencias/<INC-…>/` (cada archivo con su SHA-256 en la base), `informes/`, `regresiones/` y `laboratorio/`.
- **Identificadores únicos:** `INC-000001`, `EXP-…` y `REG-…`. Una `firma` evita duplicar la misma incidencia entre ejecuciones.
- **Contenido de cada incidencia:**
  - título, categoría y descripción;
  - gravedad, impacto, dificultad y confianza;
  - causa, con su estado: `hipotesis`, `confirmada` o `descartada`;
  - criterios de aceptación;
  - archivos afectados (ruta y SHA-256);
  - evidencias, intentos de corrección, dependencias e historial completo de cambios.
- **Estados:** `abierta → en_analisis → asignada → en_correccion → corregida_sin_verificar → verificada`, más `reabierta` y `descartada`, con las transiciones explícitas.
- **Garantías impuestas por la base (disparadores SQLite).** Se cumplen aunque alguien escriba SQL directo:
  - las incidencias **no se borran**;
  - evidencias, historial, intentos, paquetes, dependencias y regresiones son de **solo anexar**;
  - una incidencia no puede **nacer** `verificada` ni `corregida_sin_verificar`;
  - `verificada` exige una evidencia `prueba_real` **superada**, lo que es imposible en esta versión;
  - `corregida_sin_verificar` exige una evidencia **no declarativa** (estática, simulada o real) superada;
  - una causa `confirmada` exige una evidencia no declarativa;
  - una dependencia `confirmada` exige una evidencia asociada;
  - una declaración de un agente es siempre `informativa`.
- **Garantías del código:**
  - los agentes A1, A2 y A3 **no pueden** marcar como `verificada`, `descartada` ni `corregida_sin_verificar`;
  - no pueden confirmar causas ni dependencias;
  - solo aportan observaciones o declaraciones;
  - **solo el usuario descarta** y **solo el usuario desbloquea**;
  - `prueba_real` se rechaza para todos los actores mientras `MODO_B_HABILITADO = False`;
  - el grafo de dependencias `causa`/`bloquea` **no admite ciclos**;
  - cambiar la causa la devuelve a `hipotesis`.

## 2. Causa raíz, prioridades y asignación (`src/eq2/prioridad.py`)
- **La prioridad es explicable:** se devuelve con cada componente.
  - `base` = 2·gravedad + 1,5·impacto.
  - `causal` = 6·confianza·Σ certeza·(gravedad + impacto)/10, sumando las incidencias **pendientes** que esta causa o bloquea, también de forma transitiva. La certeza de un camino es la de su arista más débil: confirmada 1,0, hipótesis 0,5.
  - `efecto` = −3·certeza si la causa otra incidencia pendiente.
  - `bloqueo` = −4 si la bloquea otra pendiente.
  - `reaperturas` = +2 por cada reapertura (máximo 3).
  - `dificultad` = −0,3·dificultad: un desempate leve que **no premia lo difícil**.
- **Resultado:** se atienden primero las raíces que causan o bloquean otros errores, y una causa confirmada pesa más que una hipótesis. Las prioridades se **recalculan**, y cada recálculo queda anotado en la tabla `recalculos`, cuando aparecen errores nuevos, cambian los resultados o se planifica.
- **Planificador:**
  - causa sin confirmar → **A2 diagnostica**;
  - causa confirmada → **A1 corrige**;
  - `corregida_sin_verificar` → **A3 revisa** (falta la prueba real);
  - 2 intentos sin efecto desde el último rediagnóstico → **A2 rediagnostica** y la causa vuelve a hipótesis;
  - si se bloquea, espera a su bloqueante.
- **Sin ciclos infinitos:** la incidencia se **escala al usuario** (`bloqueada_por_limite`) al alcanzar 3 intentos, 8 tareas emitidas, o al seguir sin efecto después de 1 rediagnóstico. Los contadores salen del historial (solo anexar) y solo se reinician cuando el usuario desbloquea.
- **Límites por ronda:** como máximo 6 tareas.
- **Vista previa:** `planificar(..., aplicar=False)` no escribe nada en la base. Es la que usa `auditar.py plan`.

## 3. Recuperación de contexto (`src/eq2/contexto_incidencias.py`)
- `Empaquetador(registro, presupuesto_tokens ≥ 40)` genera paquetes sucesivos.
- **Orden:** primero las críticas (gravedad ≥ 4) y después por prioridad.
- **Contenido de cada incidencia:**
  - su cabecera y sus **criterios de aceptación**;
  - sus evidencias por relevancia: prueba real > simulación > estático > observación > declaración.
- **Lo que no cabe se conserva:** las evidencias se anotan como **omitidas** y viajan en el paquete siguiente; las incidencias, como **pendientes**.
- **Registro:** cada paquete queda en la tabla `paquetes`, con qué se incluyó, qué se omitió y qué quedó pendiente.
- **Contabilidad exacta:** se reserva el espacio de la nota de omisión, así que ningún paquete supera el presupuesto según la estimación len/3.
- **Cabecera enorme:** se recorta conservando primero el identificador y los criterios.
- **Garantía de progreso:** una evidencia que no cabe ni sola se incluye **recortada y marcada**; el texto completo sigue en la base. `todos()` tiene un tope e indica si quedó algo pendiente.
- **Declaraciones de los agentes:** `procesar_respuesta_agente()` registra «CORREGIDO: INC-…» **solo como declaración informativa**. El estado no cambia, y la base impide que esa declaración baste para pasar a `corregida_sin_verificar`.

## 4. Laboratorio (`src/eq2/laboratorio.py`)
- **Tipos de experimento:**
  - `analisis_estatico`: `ast.parse` sobre texto;
  - `simulacion`: reglas **declarativas** del tipo «si el archivo X contiene T, la prueba P falla», sin evaluar nada;
  - `prueba_motor`: el motor con agentes y ejecutor **simulados**, en una subcarpeta del laboratorio.
- **Nunca ejecuta código de los agentes.** Una prueba lo comprueba con un gancho de auditoría de Python: no hay `exec`, subprocesos, red ni `ctypes`.
- **Registro de cada experimento:** hipótesis, entradas, límites (con `ejecucion_real: false`), resultado, duración, conclusión (`apoya`, `refuta` o `no_concluyente`) y una evidencia del tipo correcto.
- **Expectativas con vocabulario cerrado:** `tipo_error`, `sin_errores`, `prueba_falla`, `prueba_pasa` y `estado_final`. Nada de expresiones.
- **Confirmación de la causa:** solo si el experimento **reproduce** el fallo.
- **Regresiones:** solo un error con causa **confirmada** y reproducido se convierte en **caso de regresión**, que es un JSON de datos, no código. `ejecutar_regresion()` comprueba que el caso sigue reproduciendo el fallo y que una versión nueva lo supera.
- **El presupuesto se ajusta a los recursos y solo se reduce:**
  - memoria no medible o por debajo de 1 GB → mínimo;
  - por debajo de 2 GB → 2 iteraciones;
  - batería por debajo del 30 % sin cargar → la mitad del tiempo.

## 5. Auditoría (`src/eq2/auditoria.py`)
- **Contenido del informe:**
  - incidencias pendientes, atendidas sin verificar, reabiertas, verificadas, descartadas y escaladas;
  - por incidencia, el recuento de evidencias por **tipo y resultado**;
  - experimentos y regresiones;
  - qué significa cada tipo de comprobación: estática, simulación o real.
- **Declaración explícita:** «Ninguna solución se ha verificado con pruebas reales.»
- **Formatos:** JSON y Markdown en `incidencias/informes/`, sin sobrescribir nunca.

## 6. Arquitectura futura (`src/eq2/extensiones.py`, solo interfaces)
- **Complementos de lenguaje:**
  - Python, con análisis estático;
  - Java, C++, C#, JavaScript y Rust, declarados y **no implementados**;
  - en ninguno se pueden ejecutar pruebas.
- **Migraciones:** `EvaluadorMigracion` devuelve una lista de comprobación con el estado `no_implementado`.
- **Versiones:** `Candidato` y `RepositorioCandidatos` modelan las versiones archivadas y los candidatos independientes. Son interfaces.
- **Configuración modular:** `ConfiguracionModular` es estricta.
  - **No puede** activar la ejecución real, el Modo B, la red, privilegios ni instalar dependencias.
  - Rechaza las claves desconocidas.
  - Solo existe la interfaz CLI.
- **Windows 11 y GUI:** siguen apoyándose en `plataforma.py`, `MIGRACION_WINDOWS.md` y los JSON de estado.

## 7. Integración opcional con el motor (`src/eq2/motor_incidencias.py`)
`Motor(..., incidencias=RegistroIncidencias)`. `ejecutar_v2.py` lo activa en `tarea_simulada` y en `tarea`.
- **En cada comprobación:**
  - los errores estáticos, las pruebas simuladas fallidas y los `BLOQUEO` de A3 se registran (o se reutilizan por su firma), con su evidencia;
  - lo que deja de reproducirse pasa a `corregida_sin_verificar`, **nunca** a `verificada`;
  - lo que reaparece se **reabre**, también en otra ejecución.
- **Si el registro falla** (error de SQLite o de E/S), la tarea **continúa**: el fallo se anota en `errores` y en `informe["incidencias"]`, y el enlace queda desactivado. No se registra nada a medias.

## 8. CLI `auditar.py`
```
python3 -B auditar.py listar [--estado E] | ver INC-000001 | prioridades | plan | paquetes --tokens 300
python3 -B auditar.py informe | demo-laboratorio | regresiones
```
- Solo usa `$TMPDIR/equipo_f2/datos_v2e2/incidencias/`.
- `plan` es una vista previa sin escrituras.
- Las entradas inválidas terminan con código 2 y un mensaje, sin trazas.
- `demo-laboratorio` crea incidencias marcadas con `origen=demo` en el mismo registro.

## 9. Otros cambios
- `VERSION = "f2-v2e2-r1"`. Los datos propios están en `datos_v2e2`, y `datos_v2e1` pasa a «carpeta anterior».
- **Pruebas heredadas modificadas (CAMBIO V2-E.2), solo por el nombre de la carpeta:**
  - `test_v2b.test_sin_modelo_no_lanza_nada_y_sale_con_error`;
  - `test_v2d.test_ciclo_simulado`;
  - `test_v2d.test_deliberacion_sin_modelo_usa_datos_v2d_y_sale_con_error`;
  - `test_v2e.test_tarea_simulada_y_supervision`.
- `validar_estatico.py` también revisa `auditar.py`.

## 10. Defectos encontrados por las pruebas nuevas, ya corregidos
1. **Bucle infinito de paquetes:** con un presupuesto pequeño, una evidencia que no cabía generaba paquetes idénticos sin fin. Se añadió la garantía de progreso.
2. **El presupuesto de tokens se superaba:** la nota de omisión no se contaba, y un paquete de 40 tokens llegaba a ocupar 65. La contabilidad ahora es exacta.
3. **Ciclo infinito en el planificador:** tras un rediagnóstico, la incidencia volvía a rediagnosticarse en cada ronda sin que A1 intentara nada más. Ahora hay contadores desde el historial, un límite de rediagnósticos y un límite de tareas por incidencia.
4. **Atribución incorrecta:** el enlace del motor reabría una incidencia descartada firmando como «usuario». Ahora firma como «motor».

## 11. Resultados (sandbox Linux; NO en Termux)
| Comprobación | Resultado |
|---|---|
| Validador estático (incluye `auditar.py`) | 0 problemas |
| Suite completa **con** `os.link` | **566/566 OK** (487 heredadas + 79 nuevas) |
| Suite completa **sin** `os.link` (simulación de Termux, incluidos los subprocesos) | **566/566 OK** |
| Solo `test_v2e2.py` | 79/79 OK |
| Mutaciones de las protecciones nuevas | 50: **49 detectadas**, 1 equivalente |
| V2-B, V2-C, V2-D, V2-E y V2-E.1 sin cambios (`sha256sum -c`) | OK (36, 41, 52, 61 y 63 archivos) |
| Suite y validador desde el ZIP extraído | ver la respuesta de entrega |

- **Mutación equivalente:** añadir «verificada» a la cadena del enlace del motor. El bucle se detiene en `corregida_sin_verificar`, y aun sin esa parada el disparador lo impediría.
- **Qué detectan las mutaciones:**
  - quitar cada disparador;
  - quitar cada permiso por actor;
  - quitar la comprobación de ciclos;
  - anular los pesos causal, de efecto, de bloqueo y de dificultad, y la certeza mínima del camino;
  - quitar cada límite del planificador (tareas, rediagnósticos, reinicio de contadores) y el tope por ronda;
  - que la vista previa escriba;
  - quitar la garantía de progreso y cada reserva de tokens;
  - quitar el orden de críticas primero y la cabecera mínima;
  - quitar los requisitos de las regresiones;
  - quitar el vocabulario cerrado y las conclusiones;
  - quitar el ajuste del presupuesto;
  - quitar el control de repetición de experimentos;
  - quitar la reapertura y la evidencia de «ya no se reproduce»;
  - quitar la captura de fallos del registro en el motor;
  - quitar las prohibiciones de la configuración;
  - que se pueda ejecutar pruebas en los complementos;
  - falsear el informe;
  - quitar la validación de la CLI.

## 12. Instalación y validación en Termux
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e2"
cd "$TMPDIR/equipo_f2/codigo_v2e2"
unzip /ruta/a/equipo_f2_v2e2.zip          # crea equipo_f2_v2e2/
cd equipo_f2_v2e2
python3 -B -I validar_estatico.py                                                      # TOTAL problemas: 0
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"     # todas OK
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_v2e2.py"  # solo las nuevas
python3 -B ejecutar_v2.py --modo tarea_simulada         # motor simulado + registro de incidencias
python3 -B auditar.py listar
python3 -B auditar.py prioridades
python3 -B auditar.py plan
python3 -B auditar.py paquetes --tokens 80
python3 -B auditar.py demo-laboratorio
python3 -B auditar.py regresiones
python3 -B auditar.py informe                           # ruta del informe .md
ls "$TMPDIR/equipo_f2"                                  # datos_v2e2 (y las carpetas anteriores intactas)
```
Nada de esto usa la red, instala paquetes, inicia `llama-server` ni toca `~/equipo-ia`. La tarea real con el modelo (`--modo tarea --iniciar-servidor-real`) no cambia respecto a V2-E.1, salvo que ahora también registra incidencias.

## 13. Limitaciones conocidas
- **Etapa 1:** el planificador y los paquetes de contexto **todavía no dirigen** el bucle del motor ni se envían al modelo. Se usan desde `auditar.py` y desde las pruebas. El motor solo **alimenta** el registro.
- **Nunca habrá incidencias `verificada`** mientras el Modo B esté deshabilitado. «Corregida» significa que ya no se reproduce en una simulación o un análisis estático; **no** que funcione.
- **Pesos provisionales:** los de la prioridad no se han calibrado con datos reales.
- **Tokens estimados:** son len/3, igual que en V2-E.1, sin contrastar con el tokenizador real.
- **Simulaciones limitadas:** las reglas de simulación son subcadenas; no detectan comportamiento. La incidencia del motor para una prueba simulada se identifica por el **nombre de la prueba**, así que dos tareas distintas con una prueba del mismo nombre comparten incidencia.
- **Bloqueos de A3:** las incidencias de `BLOQUEO` nunca se dan por corregidas automáticamente; las revisa una persona.
- **El registro no tiene tope de tamaño propio:** usa el tope de SQLite de `config.MAX_DB_BYTES`, como las otras bases. Si se alcanza, el enlace del motor se desactiva y la tarea continúa.
- **La demo comparte registro:** `demo-laboratorio` escribe en el mismo registro que las ejecuciones reales, aunque marcado con `origen=demo`.
- **Interfaces sin implementar:** los complementos de otros lenguajes, las migraciones, los candidatos, la GUI y Windows.
- **Lo heredado de V2-E.1** sigue igual: escritura no atómica en Termux (no hay `os.link`), TOCTOU y lo documentado en `LEEME_V2E1.md`.
