# Integración sin modificar los originales

Añade al `sys.path` del controlador la carpeta de este paquete y el `src` de TU copia de V2-F. No importes automáticamente el ZIP de referencia en producción. `complementos` no importa `eq2` hasta que se llama a los puentes.

## 1. Memoria con las API actuales

Se requiere el `experiencias.MemoriaEquipo` que el controlador ya haya abierto y validado. No se abren rutas aportadas por agentes, no se fusionan bases ni se crean/migran memorias desde el complemento.

```python
from complementos.v2f import MemoriaComplementada
from complementos.contexto_v2f import crear_agentes
from eq2.motor_v2f import MotorV2F

# Objetos existentes, creados/controlados por Claude:
# memoria_existente, backend_existente, ejecutor_existente, base_laboratorio
memoria = MemoriaComplementada(memoria_existente, limite_bytes=1800)
agentes = crear_agentes(backend_existente)  # No inicia servidor ni cambia presupuestos.
motor = MotorV2F(base_laboratorio, agentes, ejecutor_existente, memoria=memoria)
```

`MemoriaComplementada.bloque_prompt(agente, consulta, n=None, tarea_ref=None)` tiene la firma usada por MotorV2F y Debate. `registrar` y `resumen` delegan sin modificar la escritura existente. El dueño original debe cerrar la memoria. La recuperación no escribe `usos`; si hace falta trazabilidad adicional, `informar=callback` recibe el informe completo para que el CONTROLADOR decida dónde registrarlo. Ningún callback viene de texto de agentes.

`crear_agentes` conserva la clase y el flujo existentes: antes de `_pedir`, ajusta el JSON a los límites ya vigentes eliminando registros completos. Antes de `_llamar`, retira un bloque de memoria si el constructor total lo ha dejado incompleto. Expone `recortes_memoria` para auditar pérdidas de contexto. No aumenta CTX, max_tokens ni prioridad de la memoria. Usar este adaptador con el proxy: el proxy solo no puede impedir un recorte posterior del motor. Para Debate, usar `proteger_mensajes` en su frontera de backend si recibe estos paquetes; ese camino completo queda pendiente de integración.

API de nivel inferior:

```python
from complementos.v2f import capturar
from complementos.memoria import recuperar
instantanea = capturar(memoria_existente.apr['A1'], 'A1')
informe = recuperar(instantanea, 'contar pares en intervalo inclusivo',
                   ahora=memoria_existente.ahora(), n=4, limite_bytes=1800)
# informe: contexto, seleccion, omitidos con motivo, conflictos,
# conflictos_relevantes, requiere_revision, bytes_utf8, tokens_medidos.
```

`capturar` valida el agente y esquema antes del backup a RAM; rechaza transacciones abiertas y limita el tiempo/tamaño de la copia. La conexión fuente se usa solo para lecturas. El objeto `Instantanea` es inmutable. Debe proceder del controlador, no de JSON generado por el modelo. No es un mecanismo de autenticación entre procesos hostiles.

Se comprueban hashes del texto y la última evidencia que sustenta su estado. Se reutiliza `_comprobar_ejecucion` de V2-F para reglas declarativas registradas; las reglas regex se excluyen conservadoramente de la reevaluación en línea. El feedback humano se etiqueta como tal. Una prueba de «contiene» prueba la presencia de texto, no la verdad general de una afirmación: el alcance del verificador sigue siendo responsabilidad del controlador/auditor. Un atacante con escritura total sobre una base y sus hashes puede falsificarla: esto no es una firma criptográfica externa.

Los recuerdos `sin_verificar` observados pueden recuperarse, etiquetados como tales. Las hipótesis se excluyen por defecto (`permitir_hipotesis=True` solo por configuración del controlador). Un hecho verificado gana frente a una hipótesis contradictoria; dos hechos verificados en conflicto quedan fuera hasta revisión. Se usan relaciones de V2-F y asignaciones literales de la misma clave/ámbito. No existe un detector semántico universal de contradicciones.

Para tokens exactos, facilita `contar_tokens=tokenizer_local` y `limite_tokens=N`. Sin tokenizer, solo se garantiza el límite UTF-8 y se devuelve `tokens_medidos=None`. No se instalan tokenizadores ni se hacen llamadas al modelo para contar. El constructor de V2-F seguirá aplicando su propio presupuesto total, que puede omitir toda la memoria.

## 2. Selección de herramientas

```python
from complementos.herramientas import Contexto, Solicitud, seleccionar
from complementos.v2f import registro_actual

ctx = Contexto(agente_actual, despachador.contexto, despachador.permitido)
peticion = Solicitud('comprobar_comportamiento', tuple(archivos.keys()),
                    casos=len(casos_validados), lenguaje='python')
recomendacion = seleccionar(peticion, ctx, registro_actual())
```

Necesidades: `comprobar_sintaxis`, `comprobar_comportamiento`, `ejecutar_casos`, `analizar_lua`, `inspeccionar_zip`, `simular_escenario`. Una necesidad desconocida produce abstención. La salida contiene `herramienta`, `satisface`, `estado`, `alternativas`, `descartes`, `intervencion_humana` y `ejecuciones=0`.

Un resultado es una PROPUESTA. El controlador mantiene el despacho explícito de Claude y vuelve a comprobar argumentos, ruta, identidad y autorización al usarla. No llames a funciones por nombres arbitrarios ni uses `eval`, `exec` o shell. `satisface=False` significa que el objetivo sigue sin verificarse; el análisis estático no sustituye una prueba de comportamiento.

`Contexto`, el registro y `huella_entrada` deben construirse desde estado confiable del supervisor, nunca de recuerdos, planes ni diagnósticos. `autorizado` exige un bool real. Para evitar repetir fallos, el controlador calcula SHA-256 del código/argumentos completos y pasa `Intento(herramienta, huella_entrada, categoria)` mediante `intentos`. Un intento con esos mismos bytes no se recomienda de nuevo; un cambio de entrada permite una nueva evaluación. Esto no concede permiso para ejecutar código: sigue siendo necesaria la autorización y el aislamiento adecuados. No se eleva a A1/A3 a los permisos de A2.

## 3. Diagnóstico auxiliar

`diagnosticar(registro, huella_codigo, anteriores=())` clasifica sintaxis, dependencias, lógica, permisos, recursos, ejecución o desconocido. Retorna causa probable, evidencia breve, estrategia fija, firma y repetición. No ejecuta recomendaciones ni modifica archivos. Comparar firmas detecta repeticiones idénticas; cambios de marcas temporales pueden impedir la coincidencia. V2-F conserva su precomprobación y su historial de correcciones.

## 4. Evaluador anterior y programación

Se entrega íntegro `evaluador_anterior/evaluacion_multiagente_v1`: código `evalua/`, CLI, fixtures, pruebas y evidencias originales. Su `ejemplos/integracion.py` conecta un callback `solicitud -> Respuesta` sin abrir red por sí mismo.

Para las tres tareas nuevas de programación, añade esa carpeta al `sys.path` y llama a `evaluacion.ocultos.evaluar_programacion(adaptador, salida_nueva)`. El adaptador es el mismo `evalua.AdaptadorFuncion` anterior. El evaluador da al agente solo `casos_publicos()`, que incluyen enunciado y tres candidatas de código. Los casos reservados, resultados esperados y decisiones de puntuación no se envían en el prompt. No se da al agente acceso al filesystem del evaluador.

Se evalúan funciones fijas revisables del catálogo, no texto Python del modelo. No mide generación libre. El protocolo mantiene tres llamadas por condición, mismo modelo, parámetros y presupuesto: SOLO se revisa; A1 propone, A2 propone independientemente y A3 audita. El criterio final es la tercera respuesta, nunca la mayoría ni el oráculo. Los desacuerdos, errores por consenso, tiempos, tokens reportados y errores/inconclusiones conservan las métricas previas.

Conectar Qwen y medir el efecto final de estos complementos requiere una ronda posterior autorizada: mismo GGUF/servidor/semillas/contexto, memorias congeladas e iguales, comparación pareada con/sin complementos. El backend V2-F inspeccionado fija algunos parámetros internamente; el adaptador debe comprobar que cumple las semillas y parámetros solicitados, o declarar la condición no comparable. No falsificar tokens ni equiparar el guion con un modelo real.
