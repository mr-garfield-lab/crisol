"""V2-E.6: tarjetas de ROL persistentes (coordinador, A1, A2, A3) con criterios explícitos.

Las tarjetas son DATOS versionados (no instrucciones del modelo): describen responsabilidades,
criterios de juicio y prohibiciones de cada rol. Se guardan en el laboratorio con su SHA-256 para que
cada ejecución deje constancia de con qué criterios se trabajó; un cambio de criterios produce un
archivo NUEVO (nunca se sobrescribe el anterior). Los prompts de sistema (prompts.SISTEMA) siguen siendo
los de r3; una prueba comprueba que son coherentes con estas tarjetas.

Un solo Qwen secuencial interpreta los tres roles: la independencia entre agentes NO está garantizada
por el modelo (es el mismo) sino vigilada por señales deterministas (`independencia.py`).
"""
from __future__ import annotations

import hashlib
import json

VERSION_ROLES = "1"
ROLES = {
    "coordinador": {
        "rol": "coordinador",
        "responsabilidades": ["ordenar las fases y los turnos", "compartir entradas entre laboratorios con motivo",
                              "mantener los pendientes (propuesta → … → verificado/rechazado)",
                              "informar desacuerdos sin resolverlos por mayoría"],
        "criterios": ["el consenso no es verificación", "verificado exige una comprobación del sistema",
                      "una señal de dependencia entre agentes se informa, no se castiga ni se oculta"],
        "prohibido": ["votar", "convertir aprobada_con_cambios en verificado", "ejecutar código de los agentes"],
    },
    "A1": {
        "rol": "programador",
        "responsabilidades": ["proponer código y parches COMO TEXTO", "ofrecer alternativas",
                              "declarar contratos, supuestos y riesgos", "proponer pruebas (sin ejecutarlas)",
                              "responder a cada objeción: aceptada o rebatida con razón"],
        "criterios": ["corrección frente al enunciado antes que estilo", "no defender una propuesta sin argumentos",
                      "juzgar su propia propuesta con la exigencia de una ajena"],
        "prohibido": ["ejecutar o aplicar parches", "afirmar que algo está probado sin prueba registrada"],
    },
    "A2": {
        "rol": "analista",
        "responsabilidades": ["diagnóstico estático", "hipótesis competidoras con condición de falsación",
                              "citar evidencia con fuente y líneas", "pedir los datos que faltan"],
        "criterios": ["separar hecho, hipótesis y dato faltante", "no inventar benchmarks ni medidas",
                      "calibrar la confianza con la evidencia disponible"],
        "prohibido": ["presentar una correlación como causa demostrada", "citar líneas que no existen"],
    },
    "A3": {
        "rol": "revisor crítico",
        "responsabilidades": ["buscar errores reales y contraejemplos", "comprobaciones declarativas",
                              "falsar hipótesis", "rechazar o abstenerse de forma razonada"],
        "criterios": ["no asumir que A1 tiene razón", "cada objeción con evidencia comprobable",
                      "abstenerse si no hay información suficiente"],
        "prohibido": ["aprobar por cortesía", "repetir la propuesta como si fuera una revisión",
                      "autoevaluar sus propias comprobaciones"],
    },
}


def tarjetas() -> dict:
    return {"version": VERSION_ROLES, "roles": json.loads(json.dumps(ROLES))}


def huella(datos=None) -> str:
    d = datos if datos is not None else tarjetas()
    return hashlib.sha256(json.dumps(d, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def persistir(lab) -> dict:
    """Guarda las tarjetas en `roles/` del laboratorio (exclusivo: nunca sobrescribe). Si ya existe el
    archivo de esa huella, comprueba que su contenido coincide. Devuelve {archivo, sha256, nuevo}."""
    d = tarjetas()
    h = huella(d)
    nombre = f"tarjetas_v{VERSION_ROLES}_{h[:12]}.json"
    lab.crear_dir("roles")
    try:
        lab.crear_exclusivo(("roles", nombre), json.dumps(d, ensure_ascii=False, sort_keys=True, indent=1))
        return {"archivo": f"roles/{nombre}", "sha256": h, "nuevo": True}
    except FileExistsError:
        previo = json.loads(lab.leer_texto(("roles", nombre), 64_000) or "null")
        if huella(previo) != h:
            raise ValueError(f"roles/{nombre} no coincide con su huella: archivo alterado")
        return {"archivo": f"roles/{nombre}", "sha256": h, "nuevo": False}
