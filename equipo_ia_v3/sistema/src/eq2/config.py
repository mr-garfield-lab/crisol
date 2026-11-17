"""Constantes y límites de la fase 2 (V0-V1).

Todos los límites son PROVISIONALES hasta medirlos con el modelo real (V2+).
La estimación de tokens es una aproximación conservadora, no una medida.
"""
from __future__ import annotations

from pathlib import Path

HOST = "127.0.0.1"          # reservado para V2; en V0-V1 no se usa red
CTX = 1024                   # contexto por defecto (aprobado). V2-D: --ctx 2048 es opcional y explícito
CTX_PERMITIDOS = (1024, 2048, 2560, 3072)   # V2-E.6: 2560/3072 solo vía perfiles (perfiles_contexto)
PERFIL_CONTEXTO = None       # V2-E.6: perfil aplicado (None = biblioteca con CTX=1024)
MARGEN_CTX = 48              # tokens de seguridad ante estimación imprecisa
# ESTIMACIÓN PROVISIONAL de tokens (len/3). No está validada contra el servidor
# real; los valores medidos se guardarán en las columnas tokens_* de `turnos`
# (NULL mientras el backend sea simulado). No tomar como medida.
ESTIMACION_TOKENS = "provisional: len/3, sin validar contra el servidor real"
CHARS_POR_TOKEN = 3
TOKENS_POR_MENSAJE = 8       # sobrecarga estimada de la plantilla de chat

AGENTES = ("A1", "A2", "A3")

# (orden previsto, fase, agente). Los votos son ciegos (no ven votos ajenos).
PLAN = (
    (1, "analisis", "A2"),
    (2, "propuesta", "A1"),
    (3, "revision", "A3"),
    (4, "replica", "A1"),
    (5, "voto", "A2"),
    (6, "voto", "A3"),
    (7, "voto", "A1"),
)

# V2-D: propuesta 220 -> 320 y réplica 160 -> 240 (las dos fases que se truncaron en la
# deliberación real de V2-C). Análisis, revisión y voto sin cambios.
MAX_TOKENS = {"analisis": 160, "propuesta": 320, "revision": 160,
              "replica": 240, "voto": 120}
# V2-E.5: petición de evidencia (opcional, como máximo una por tarea). Aparte de MAX_TOKENS a propósito:
# las fases del PLAN no cambian.
MAX_TOKENS_ACLARACION = 160


def max_tokens_fase(fase: str) -> int:
    return MAX_TOKENS_ACLARACION if fase == "aclaracion" else MAX_TOKENS[fase]

POSTURAS = ("aprobar", "aprobar_con_cambios", "rechazar", "abstencion")

# Límites de operación
MAX_TAREAS_SESION = 3
# V2-D: 10 -> 12 = 7 del plan + 2 continuaciones (propuesta y réplica) + 3 reintentos de voto.
MAX_LLAMADAS_TAREA = 12
# V2-E.5: la aclaración (si se activa) cuenta UNA llamada más y nunca más de una por tarea.
LLAMADAS_ACLARACION = 1
MAX_REINTENTOS_VOTO = 1          # por voto
SEG_POR_LLAMADA = 240
SEG_POR_TAREA = 20 * 60
SEG_POR_SESION = 60 * 60
MAX_TAREA_CHARS = 600            # recortado desde 1500 por el contexto de 1024
# V2-D: 1200 -> 2400. Con 320 + 200 tokens una propuesta podía superar 1200 caracteres y se
# recortaba EN SILENCIO al guardarla. Ahora, si aun así se supera, el turno cuenta como truncado.
MAX_TURNO_CHARS = 2400
MAX_MEMORIA_ENTRADAS = 200
MAX_MEMORIA_CHARS = 500
MAX_DB_BYTES = 5 * 1024 * 1024
MEMORIAS_POR_PROMPT = 3
MEMORIA_PROMPT_CHARS = 150
CAP_MEMORIAS_PROMPT = 800        # V2-E.6 (r3: 500): las memorias llevan metadatos (~90 caracteres c/u)
APRENDIZAJE_HABILITADO = True    # V2-E.6: base de aprendizaje por agente (aprendizaje/<agente>.db)

# Vigilancia
UMBRAL_MEM_KB = 300_000
MUESTRAS_BAJAS_CONSECUTIVAS = 3
FALLOS_MONITOR_MAX = 3
BATERIA_MIN_PCT = 20

# Caps de caracteres de cada bloque de historial dentro de un prompt (V0-V2C; se conservan
# por compatibilidad, pero V2-D usa CAPS_BLOQUE por fase).
CAP_ANALISIS = 250
CAP_PROPUESTA = 400
CAP_REVISION = 300
CAP_REPLICA = 400

# V2-D: caps por (fase que recibe el prompt, bloque), para CTX=1024; se escalan con CTX/1024.
# Antes la revisión y los votantes veían solo 400 caracteres de la propuesta.
CAPS_BLOQUE = {
    "propuesta": {"analisis": 450},
    "revision": {"analisis": 200, "propuesta": 1100},
    "replica": {"analisis": 150, "propuesta": 900, "revision": 450},
    "voto": {"propuesta_final": 1300, "revision": 250},
    "aclaracion": {"propuesta": 1100, "objeciones": 450},           # V2-E.5
}


def cap_bloque(fase: str, bloque: str) -> int:
    return int(CAPS_BLOQUE[fase][bloque] * CTX / 1024)

# --- V2-D: continuación y truncamiento semántico ------------------------------------------
FASES_CON_CONTINUACION = ("propuesta", "replica")
FASES_CON_MARCA_FIN = ("propuesta", "replica")
MARCA_FIN = "FIN"
MAX_CONTINUACIONES_POR_FASE = 1
MAX_TOKENS_CONTINUACION = 200
MIN_TOKENS_CONTINUACION = 48      # si queda menos espacio en el contexto, no se continúa
MARGEN_CONTINUACION = 16



def presupuesto_prompt(fase: str) -> int:
    """Tokens máximos de prompt para una fase: CTX - generación - margen."""
    return CTX - MAX_TOKENS[fase] - MARGEN_CTX


_PROYECTO_PROHIBIDO = "equipo-ia"

# --- V2: servidor llama.cpp local (solo 127.0.0.1) ---------------------------------
PUERTO = 8089
HILOS = 4
NP = 1                            # una sola ranura
MODELO_PARTES = (_PROYECTO_PROHIBIDO, "modelos", "qwen-coder-3b.gguf")   # bajo $HOME, SOLO LECTURA
MIN_MODELO_BYTES = 10 ** 9        # igual que prueba3
MAX_CARGA_S = 120
MAX_RESP_BYTES = 1_000_000
MAX_CABECERAS_BYTES = 16 * 1024
TEMPERATURA = 0
SEMILLA = 1
TOPE_MAX_TOKENS = 800            # V2-D: 400; V2-E: 700; V2-E.6: 800 (solo el perfil experimental lo usa)
GRACIA_TERM_S = 10
GRACIA_KILL_S = 5
INTERVALO_MONITOR = 2.0
INTERVALO_SONDEO_S = 1.0
CRITICAS = ("MemAvailable", "VmRSS", "majflt")
ENV_SENSIBLE = r"KEY|TOKEN|SECRET|PASSWORD|ANTHROPIC|OPENAI"


def ruta_modelo() -> Path:
    """Ruta del modelo (solo lectura). Única ruta bajo ~/equipo-ia que el código puede leer."""
    return Path.home().joinpath(*MODELO_PARTES)


def fuera_de_proyecto(ruta) -> bool:
    """True si `ruta` NO está dentro de ~/equipo-ia (el proyecto existente)."""
    try:
        r = Path(ruta).expanduser().resolve()
        prohibido = (Path.home() / _PROYECTO_PROHIBIDO).resolve()
    except (OSError, RuntimeError):
        return False
    return r != prohibido and prohibido not in r.parents


# --- V2-B (deliberación real) -------------------------------------------------------------
CARPETA_V2B = "datos_v2b"
TAREA_V2B = "Diseña una función Python que ordene una lista de enteros sin modificar la lista original."
# Motivos de aborto de TAREA que indican fallo de infraestructura: la sesión se detiene y no se
# inician más tareas (decisión de GPT-6). Los votos inválidos siguen el protocolo de reintento/abstención.
MOTIVOS_TAREA_INFRAESTRUCTURA = ("inferencia_fallida", "tiempo_tarea")

# --- V2-C (fiabilidad de votos y truncados) --------------------------------------------------
CARPETA_V2C = "datos_v2c"

# --- V2-D -----------------------------------------------------------------------------------
CARPETA_V2D = "datos_v2d"
# V2-E.1: también datos_v2e (la versión corregida usa su propia carpeta y nunca escribe en la de V2-E)
CARPETAS_ANTERIORES = ("datos_v2", "datos_v2b", "datos_v2c", "datos_v2d", "datos_v2e", "datos_v2e1", "datos_v2e2", "datos_v2e3", "datos_v2e4", "datos_v2e4r2", "datos_v2e5", "datos_v2e5r2", "datos_v2e5r3", "lab_v2e6", "lab_v2e6r2", "lab_v2e6r3", "lab_v2e7", "lab_v2e7r2", "lab_v2e7r3", "lab_v2f")

# Ejecutor (arquitectura; en V2-D solo existe el ejecutor SIMULADO)
EJECUTOR_MAX_ITERACIONES = 3
EJECUTOR_MAX_ARCHIVOS = 5
EJECUTOR_MAX_BYTES_ARCHIVO = 20_000
EJECUTOR_SEG_POR_EJECUCION = 30
EJECUTOR_MEM_MB = 256
EJECUTOR_HERRAMIENTAS = ("pruebas_python", "analisis_estatico")   # lista cerrada (V2-E: + estático)
EJECUTOR_EXTENSIONES = (".py", ".txt", ".md", ".json")

# --- V2-E -----------------------------------------------------------------------------------
CARPETA_V2E = "datos_v2e"           # carpeta de V2-E (anterior): V2-E.1 no la usa
CARPETA_V2E1 = "datos_v2e1"         # V2-E.1 (anterior): V2-E.2 no la usa
CARPETA_V2E2 = "datos_v2e2"         # V2-E.2 (anterior): V2-E.3 no la usa
CARPETA_V2E3 = "datos_v2e3"         # V2-E.3 (anterior): V2-E.4 no la usa
CARPETA_V2E4 = "datos_v2e4"         # V2-E.4 r1 (anterior): V2-E.4-r2 no la usa (esquema distinto)
CARPETA_V2E4R2 = "datos_v2e4r2"     # V2-E.4-r2 (anterior): V2-E.5 no la usa
CARPETA_V2E5 = "datos_v2e5"         # V2-E.5 (anterior): V2-E.5-r2 no la usa
CARPETA_V2E5R2 = "datos_v2e5r2"     # V2-E.5-r2 (anterior): V2-E.5-r3 no la usa
CARPETA_V2E5R3 = "datos_v2e5r3"     # V2-E.5-r3 (anterior): V2-E.6 no la usa ni la modifica
CARPETA_V2E6 = "lab_v2e6"           # V2-E.6: TODO (datos, verificación, auditoría, retos) vive aquí dentro
CARPETA_V2E6R2 = "lab_v2e6r2"       # V2-E.6-r2: carpeta propia (la de V2-E.6 no se toca)
CARPETA_V2E6R3 = "lab_v2e6r3"       # V2-E.6-r3: carpeta propia (las de V2-E.6 y V2-E.6-r2 no se tocan)
CARPETA_V2E7 = "lab_v2e7"           # V2-E.7: equipo operativo (tareas LAB-NNN); las anteriores no se tocan
CARPETA_V2E7R2 = "lab_v2e7r2"       # V2-E.7-r2: integración PZ ModLab 0.2; las anteriores no se tocan
CARPETA_V2E7R3 = "lab_v2e7r3"       # V2-E.7-r3: auditoría de A3 en modlab_pz; las anteriores no se tocan
CARPETA_V2F = "lab_v2f"             # V2-F: capacidades (plan, debate, memoria, autocorrección, herramientas, banco)
CARPETA_V2F1 = "lab_v2f1"           # V2-F.1: función supervisada (A1/A2/A3), interfaces para Codex; las anteriores no se tocan
CARPETA_ACTUAL = CARPETA_V2F1         # único punto que fija la carpeta de la versión en curso

# --- V2-E.5-r2: personalidad (OPCIONAL; desactivada por defecto) -------------------------------
# La elección con el modelo solo se hace con una orden explícita del usuario
# (ejecutar_v2.py --modo personalidad --autorizar-eleccion-personalidad --iniciar-servidor-real).
# Ninguna deliberación, tarea ni motor la invoca, y el perfil NO se inyecta en los prompts.
PERSONALIDAD_ELECCION_HABILITADA = False
PERSONALIDAD_ADAPTACION_AUTOMATICA = False      # no existe aplicación automática en esta versión
PERSONALIDAD_MAX_TOKENS = 120                    # por respuesta del modelo
PERSONALIDAD_MAX_INTENTOS_AGENTE = 2             # 1 llamada + 1 reintento por agente y elección
PERSONALIDAD_MAX_INTENTOS_DIA = 4                # llamadas por agente en 24 h
PERSONALIDAD_MAX_RESPUESTA_CHARS = 1500
PERSONALIDAD_MAX_DB_BYTES = 2 * 1024 * 1024
PERSONALIDAD_MAX_EXPERIENCIAS_ACTIVAS = 200      # por agente (hay un tope duro en la base)
PERSONALIDAD_MAX_CAMBIOS_PENDIENTES = 3          # por agente
PERSONALIDAD_HORAS_ENTRE_PROPUESTAS = 24         # frecuencia máxima de adaptación (por agente)
PERSONALIDAD_MIN_EXPERIENCIAS = 3                # experiencias VERIFICADAS repetidas para proponer
# --- V2-E.5-r2: laboratorios individuales (cuadernos por agente) -----------------------------
LAB_MAX_OPERACIONES_SESION = 100                 # escrituras por cuaderno y proceso
# V2-E.4: MÁXIMOS DUROS de la investigación automática (un presupuesto puede ser menor, nunca mayor).
INVESTIGACION_MAXIMOS = {"max_hipotesis_por_incidencia": 5, "max_experimentos_por_incidencia": 10,
                         "max_experimentos_por_ejecucion": 20, "max_regresiones_por_incidencia": 3,
                         "seg_max_investigacion": 120.0}
CTX_PRINCIPAL = 2048        # contexto experimental principal (por defecto en el ejecutable)
# La biblioteca mantiene CTX = 1024 (alternativa) para que las pruebas heredadas sigan valiendo.

# Motor autónomo: MÁXIMOS DUROS. Un presupuesto por tarea puede ser menor, nunca mayor.
MOTOR_MAX_ITERACIONES_CORRECCION = 3
MOTOR_MAX_LLAMADAS = 14         # plan + generar + revisar + 3 x (evaluar + corregir + revisar) + 2
MOTOR_SEG_TOTAL = 30 * 60
FS_SEG_TOTAL = 45 * 60             # V2-F.1: función supervisada (hasta 3 rondas de A1/A2/A3 con Qwen en el S23)
MOTOR_SEG_POR_PRUEBA = 30
MOTOR_MAX_ARCHIVOS = 8
MOTOR_MAX_BYTES_ARCHIVO = 20_000
MOTOR_MAX_BYTES_TOTAL = 64_000
MOTOR_MAX_PROFUNDIDAD = 3       # componentes de ruta relativa (p. ej. paquete/sub/modulo.py)
MOTOR_MAX_TOKENS = {
    1024: {"plan": 160, "generar": 400, "revisar": 160, "evaluar": 120},
    2048: {"plan": 200, "generar": 640, "revisar": 200, "evaluar": 160},
}

# Modo B (ejecución real aislada): DESHABILITADO. No hay aislamiento real demostrado en Termux.
MODO_B_HABILITADO = False


def max_tokens_motor(paso: str) -> int:
    # V2-E.6: si un perfil registró presupuestos para este CTX exacto, se usan; si no, los de V2-E.
    return (MOTOR_MAX_TOKENS.get(CTX) or MOTOR_MAX_TOKENS[2048 if CTX >= 2048 else 1024])[paso]
