"""V2-E.6: perfiles de CONTEXTO y presupuestos de tokens, conservadores y adaptables.

Perfiles (el servidor se lanza con `-c ctx`; los presupuestos de salida van APARTE):
  seguro        1024  presupuestos de V2-C/V2-D (la biblioteca por defecto: pruebas heredadas)
  referencia    2048  igual que V2-E.5-r3 (por defecto en el ejecutable)
  ampliado      2560  +25 % de salida en las fases largas; exige RAM disponible suficiente
  experimental  3072  +50 %; exige RAM suficiente Y aceptación explícita (--aceptar-experimental)
Retroceso automático a un perfil seguro si la RAM no se puede medir, no alcanza, el servidor tiene un
contexto menor o no se aceptó el experimental. Cada decisión se devuelve con sus MOTIVOS (trazable).
El voto no crece (su formato es corto) y ningún presupuesto supera TOPE_MAX_TOKENS.

NADA de esto está medido con Qwen real en esta entrega: los umbrales de RAM son estimaciones
conservadoras documentadas (KV-cache ~ proporcional al contexto) y deben confirmarse en el dispositivo.
"""
from __future__ import annotations

from . import config

PERFILES = {
    "seguro": {"ctx": 1024, "mem_min_kb": 0, "experimental": False,
               "max_tokens": {"analisis": 160, "propuesta": 320, "revision": 160, "replica": 240, "voto": 120},
               "aclaracion": 160, "continuacion": 200,
               "motor": {"plan": 160, "generar": 400, "revisar": 160, "evaluar": 120}},
    "referencia": {"ctx": 2048, "mem_min_kb": 1_200_000, "experimental": False,
                   "max_tokens": {"analisis": 160, "propuesta": 320, "revision": 160, "replica": 240, "voto": 120},
                   "aclaracion": 160, "continuacion": 200,
                   "motor": {"plan": 200, "generar": 640, "revisar": 200, "evaluar": 160}},
    "ampliado": {"ctx": 2560, "mem_min_kb": 2_000_000, "experimental": False,
                 "max_tokens": {"analisis": 200, "propuesta": 400, "revision": 200, "replica": 300, "voto": 120},
                 "aclaracion": 200, "continuacion": 240,
                 "motor": {"plan": 240, "generar": 700, "revisar": 240, "evaluar": 200}},
    "experimental": {"ctx": 3072, "mem_min_kb": 2_800_000, "experimental": True,
                     "max_tokens": {"analisis": 240, "propuesta": 480, "revision": 240, "replica": 360, "voto": 120},
                     "aclaracion": 240, "continuacion": 280,
                     "motor": {"plan": 280, "generar": 800, "revisar": 280, "evaluar": 240}},
}
ORDEN = ("seguro", "referencia", "ampliado", "experimental")
POR_DEFECTO = "referencia"
# Límites ESTRICTOS de generación acumulada (suma de max_tokens pedidos) por tarea y por sesión,
# escalados con el perfil. Ninguna tarea puede pedir más aunque queden llamadas.
TOKENS_TAREA = {"seguro": 2_600, "referencia": 2_600, "ampliado": 3_200, "experimental": 3_900}
TOKENS_SESION = {"seguro": 7_800, "referencia": 7_800, "ampliado": 9_600, "experimental": 11_700}
# Reservas del prompt (tokens estimados), documentadas para cada fase.
RESERVA_SISTEMA = 120
RESERVA_MEMORIA = 160


def perfil_de_ctx(ctx: int) -> str:
    for nombre in ORDEN:
        if PERFILES[nombre]["ctx"] == ctx:
            return nombre
    raise ValueError(f"contexto sin perfil: {ctx}")


def seleccionar(solicitado: str, mem_kb=None, ctx_servidor=None, aceptar_experimental=False) -> dict:
    """Decide el perfil EFECTIVO. Nunca sube por encima del solicitado; baja con motivos."""
    if solicitado not in PERFILES:
        raise ValueError(f"perfil desconocido: {solicitado!r} (válidos: {', '.join(ORDEN)})")
    motivos, efectivo = [], solicitado
    if PERFILES[efectivo]["experimental"] and not aceptar_experimental:
        motivos.append("experimental no aceptado explícitamente (--aceptar-experimental)")
        efectivo = "ampliado"
    while efectivo != "seguro":
        p = PERFILES[efectivo]
        if efectivo not in ("seguro", "referencia") and mem_kb is None:
            motivos.append(f"{efectivo}: RAM disponible no medible")
        elif mem_kb is not None and mem_kb < p["mem_min_kb"]:
            motivos.append(f"{efectivo}: RAM disponible {mem_kb} kB < {p['mem_min_kb']} kB")
        elif ctx_servidor is not None and ctx_servidor < p["ctx"]:
            motivos.append(f"{efectivo}: el servidor tiene ctx {ctx_servidor} < {p['ctx']}")
        else:
            break
        efectivo = ORDEN[ORDEN.index(efectivo) - 1]
    return {"solicitado": solicitado, "efectivo": efectivo, "retroceso": efectivo != solicitado,
            "motivos": motivos, "ctx": PERFILES[efectivo]["ctx"], "mem_kb_medida": mem_kb,
            "medido": mem_kb is not None}


def aplicar(nombre: str) -> dict:
    """Aplica el perfil a la configuración del PROCESO (como hace --ctx). Devuelve lo aplicado."""
    p = PERFILES[nombre]
    for v in list(p["max_tokens"].values()) + list(p["motor"].values()) + [p["aclaracion"], p["continuacion"]]:
        if v > config.TOPE_MAX_TOKENS:
            raise ValueError("un presupuesto supera TOPE_MAX_TOKENS")
    config.CTX = p["ctx"]
    config.MAX_TOKENS = dict(p["max_tokens"])
    config.MAX_TOKENS_ACLARACION = p["aclaracion"]
    config.MAX_TOKENS_CONTINUACION = p["continuacion"]
    motor = dict(config.MOTOR_MAX_TOKENS)
    motor[p["ctx"]] = dict(p["motor"])
    config.MOTOR_MAX_TOKENS = motor
    config.PERFIL_CONTEXTO = nombre
    return {"perfil": nombre, "ctx": config.CTX, "max_tokens": dict(config.MAX_TOKENS),
            "tokens_tarea": TOKENS_TAREA[nombre], "tokens_sesion": TOKENS_SESION[nombre]}


def presupuesto_detallado(nombre: str) -> dict:
    """Reparto por fase: salida, margen, reservas de sistema/instrucciones y memoria, e historial."""
    p = PERFILES[nombre]
    out = {}
    for fase, salida in p["max_tokens"].items():
        resto = p["ctx"] - salida - config.MARGEN_CTX - RESERVA_SISTEMA - RESERVA_MEMORIA
        out[fase] = {"ctx": p["ctx"], "salida": salida, "margen": config.MARGEN_CTX, "sistema": RESERVA_SISTEMA,
                     "memoria": RESERVA_MEMORIA, "historial_y_tarea": resto}
    return out


def tokens_tarea() -> int:
    return TOKENS_TAREA.get(getattr(config, "PERFIL_CONTEXTO", None) or perfil_de_ctx_seguro(), TOKENS_TAREA["referencia"])


def tokens_sesion() -> int:
    return TOKENS_SESION.get(getattr(config, "PERFIL_CONTEXTO", None) or perfil_de_ctx_seguro(), TOKENS_SESION["referencia"])


def perfil_de_ctx_seguro() -> str:
    try:
        return perfil_de_ctx(config.CTX)
    except ValueError:
        return "referencia"
