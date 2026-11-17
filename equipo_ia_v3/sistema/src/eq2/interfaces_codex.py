"""V2-F.1: INTERFACES para los módulos que desarrolla Codex: recuperación de memoria, selección de herramientas y
diagnóstico de errores. Este módulo NO implementa esos módulos (no se duplica el trabajo de Codex): define

  1. el CONTRATO de cada componente (typing.Protocol, comprobable con `comprobar_conformidad`);
  2. un ADAPTADOR POR DEFECTO sobre lo que ya existe en V2-F (experiencias.py, herramientas.py, autocorreccion.py),
     para que el sistema funcione hoy sin esperar a Codex;
  3. una CAPA DE VALIDACIÓN (`Componentes`) por la que pasa TODA salida de un componente, sea el de por defecto o
     uno externo. Las salidas son DATOS NO CONFIABLES:
       * nada de lo que devuelve un componente llega a config, a la política, a los permisos, al presupuesto ni al
         registro de herramientas: solo se usa como TEXTO en un prompt o como NOMBRE de herramienta que se vuelve a
         comprobar contra herramientas.REGISTRO;
       * los componentes no reciben objetos con poder (laboratorio, backend, despachador, configuración): solo
         textos, listas y diccionarios copiados;
       * lo inválido se DESCARTA y se registra en `incidencias` (nunca se corrige en silencio);
       * un componente que lanza una excepción no detiene la tarea: se usa el adaptador por defecto y se registra.

Contratos (VERSION_INTERFAZ = "eq2-codex-1"):

  RecuperadorMemoria.recuperar(agente: str, consulta: str, n: int) -> list[dict]
      cada dict: {"texto": str, "tipo": hecho|hipotesis|leccion|criterio, "fuente": una de aprendizaje.FUENTES,
                  "estado": hipotesis|sin_verificar|verificada_por_prueba, opcionales: "id", "fecha", "confianza"}
      Los textos pasan además por aprendizaje.analizar_contenido: lo instructivo o en cuarentena se descarta.
  SelectorHerramientas.seleccionar(necesidad: str, contexto: dict) -> dict
      necesidad: comprobar_sintaxis | comprobar_comportamiento | ejecutar_casos
      contexto: {"agente", "flujo", "autorizado", "ejecucion_dinamica": "bloqueada"|"permitida", "candidatas": [...]}
      devuelve {"herramienta": <nombre del REGISTRO>, "motivo": str}. La elección se acepta solo si la herramienta
      existe, sirve para esa necesidad, la puede usar ese agente en ese flujo, tiene la autorización que exige y NO
      ejecuta código cuando la ejecución dinámica está bloqueada; si no, se usa la elección determinista por defecto.
  DiagnosticoErrores.diagnosticar(errores: list[dict], archivos: dict[str, str]) -> list[dict]
      errores: hechos del controlador ({"tipo", "archivo", "linea", "detalle"}); devuelve hipótesis
      {"causa": str, "archivo": str|None, "linea": int|None, "propuesta": str, "confianza": baja|media|alta}
      para el prompt de A1. Un diagnóstico no cambia el flujo ni el veredicto: A1 decide qué corregir y el
      controlador vuelve a comprobarlo.

Para conectar un módulo de Codex: `Componentes(recuperador=..., selector=..., diagnostico=...)` y pasarlo a
`funcion_supervisada.FuncionSupervisada(componentes=...)` (no hay carga dinámica de módulos: el validador estático
prohíbe importlib). Antes, `comprobar_conformidad(objeto, "recuperador"|"selector"|"diagnostico")`.
"""
from __future__ import annotations

import inspect
from typing import Protocol, runtime_checkable

from . import aprendizaje, autocorreccion, herramientas, sanea

VERSION_INTERFAZ = "eq2-codex-1"
MAX_RECUERDOS = 5
MAX_TEXTO_RECUERDO = 300
MAX_DIAGNOSTICOS = 6
MAX_CAMPO = 200
CONFIANZAS = ("baja", "media", "alta")
ESTADOS_RECUERDO = ("hipotesis", "sin_verificar", "verificada_por_prueba")
NECESIDADES = {                                   # necesidad -> herramientas que la satisfacen (la 1.ª es la principal)
    "comprobar_sintaxis": ("analisis_estatico",),
    "comprobar_comportamiento": ("pruebas_python", "analisis_estatico"),
    "ejecutar_casos": ("ejecutar_casos", "analisis_estatico"),
}


# --- contratos -------------------------------------------------------------------------------------------------
@runtime_checkable
class RecuperadorMemoria(Protocol):
    nombre: str

    def recuperar(self, agente: str, consulta: str, n: int) -> list: ...


@runtime_checkable
class SelectorHerramientas(Protocol):
    nombre: str

    def seleccionar(self, necesidad: str, contexto: dict) -> dict: ...


@runtime_checkable
class DiagnosticoErrores(Protocol):
    nombre: str

    def diagnosticar(self, errores: list, archivos: dict) -> list: ...


CONTRATOS = {"recuperador": (RecuperadorMemoria, "recuperar", 3), "selector": (SelectorHerramientas, "seleccionar", 2),
             "diagnostico": (DiagnosticoErrores, "diagnosticar", 2)}


# --- adaptadores por defecto (sobre módulos existentes de V2-F) ------------------------------------------------------
class RecuperadorExperiencias:
    """experiencias.MemoriaEquipo: la base INDIVIDUAL de cada agente (aprendizaje/a1.db, a2.db, a3.db)."""
    nombre = "experiencias_v2f"

    def __init__(self, memoria, tarea_ref=None):
        self._mem, self._tarea_ref = memoria, tarea_ref

    def recuperar(self, agente, consulta, n):
        if self._mem is None:
            return []
        return self._mem.apr[agente].recuperar(consulta, n=n, tarea_ref=self._tarea_ref)


class SelectorRegistro:
    """herramientas.seleccionar: tabla determinista con sustitución por análisis estático sin autorización."""
    nombre = "registro_v2f"

    def seleccionar(self, necesidad, contexto):
        permitido = bool(contexto.get("autorizado")) and contexto.get("ejecucion_dinamica") == "permitida"
        s = herramientas.seleccionar(necesidad, permitido)
        return {"herramienta": s["herramienta"], "motivo": s["nota"] or "elección principal del registro"}


_PROPUESTAS = {
    "sintaxis": "corrige la sintaxis en esa línea (dos puntos, paréntesis, indentación) y reescribe el archivo completo",
    "no_analizable": "simplifica el archivo: el analizador no pudo procesarlo",
    "nombre_no_definido": "define ese nombre en el módulo o deja de importarlo",
    "modulo_inexistente": "usa solo la biblioteca estándar de cálculo o el propio archivo",
    "demasiado_grande": "reduce el archivo a lo que pide la tarea",
    "funcion_ausente": "define la función con el nombre exacto que pide la tarea, en el nivel superior del archivo",
    "lista_blanca": "elimina esa operación: no se admite (archivos, sistema, red, introspección)",
    "oraculo_inaplicable": "ajusta la firma para que acepte los argumentos de los casos del usuario",
    "sin_codigo": "escribe 'ARCHIVO: solucion.py' y debajo el código completo en un bloque ```",
}


class DiagnosticoEstatico:
    """Diagnóstico mínimo a partir de los HECHOS del controlador (sin modelo). Es el sustituto hasta que exista el
    módulo de Codex; para los cuatro tipos de V2-F usa la misma redacción que autocorreccion.diagnostico_estatico."""
    nombre = "estatico_v2f"

    def diagnosticar(self, errores, archivos):
        out = []
        for e in errores:
            tipo = e.get("tipo", "")
            if tipo in autocorreccion.TIPOS_BLOQUEANTES and tipo != "demasiado_grande":
                causa = autocorreccion.diagnostico_estatico([_error_v2f(e)]).split("\n")[1].lstrip("- ")
            else:
                causa = f"{tipo}: {e.get('detalle') or ''}".strip(": ")
            out.append({"causa": causa, "archivo": e.get("archivo"), "linea": e.get("linea"),
                        "propuesta": _PROPUESTAS.get(tipo, "corrige el problema indicado"), "confianza": "alta"})
        return out


def _error_v2f(e) -> dict:
    """Hecho del controlador -> forma que espera autocorreccion.diagnostico_estatico."""
    d = {"tipo": e.get("tipo"), "archivo": e.get("archivo") or "?", "linea": e.get("linea")}
    if e.get("tipo") == "sintaxis":
        d["mensaje"] = e.get("detalle") or ""
    elif e.get("tipo") == "nombre_no_definido":
        d["nombre"], d["modulo"] = e.get("nombre"), e.get("modulo")
    elif e.get("tipo") == "modulo_inexistente":
        d["modulo"] = e.get("modulo")
    return d


# --- validación ------------------------------------------------------------------------------------------------
def validar_recuerdos(lista, n) -> tuple:
    """(válidos, descartes). Cada válido: {id, tipo, texto, fuente, estado, fecha, confianza} saneados."""
    validos, descartes = [], []
    if not isinstance(lista, list):
        return [], [{"motivo": "la salida no es una lista"}]
    for i, m in enumerate(lista):
        if len(validos) >= min(int(n), MAX_RECUERDOS):
            descartes.append({"i": i, "motivo": f"más de {min(int(n), MAX_RECUERDOS)} recuerdos"})
            continue
        if not isinstance(m, dict) or not isinstance(m.get("texto"), str) or not m["texto"].strip():
            descartes.append({"i": i, "motivo": "recuerdo sin texto"})
            continue
        if m.get("tipo") not in aprendizaje.TIPOS:
            descartes.append({"i": i, "motivo": f"tipo no admitido: {str(m.get('tipo'))[:20]}"})
            continue
        if m.get("fuente") not in aprendizaje.FUENTES:
            descartes.append({"i": i, "motivo": f"fuente no admitida: {str(m.get('fuente'))[:20]}"})
            continue
        if m.get("estado", "sin_verificar") not in ESTADOS_RECUERDO:
            descartes.append({"i": i, "motivo": f"estado no vigente: {str(m.get('estado'))[:20]}"})
            continue
        texto = sanea.limpiar(m["texto"], MAX_TEXTO_RECUERDO)
        v = aprendizaje.analizar_contenido(texto)
        if v["veredicto"] != "aceptado":
            descartes.append({"i": i, "motivo": f"contenido {v['veredicto']}: {(v['motivos'] or ['?'])[0][:80]}"})
            continue
        validos.append({"id": sanea.limpiar(str(m.get("id") or f"R{i + 1}"), 40), "tipo": m["tipo"], "texto": texto,
                        "fuente": m["fuente"], "estado": m.get("estado", "sin_verificar"),
                        "fecha": sanea.limpiar(str(m.get("fecha") or ""), 10),
                        "confianza": m.get("confianza") if m.get("confianza") in CONFIANZAS else "baja",
                        "tarea_ref": sanea.limpiar(str(m.get("tarea_ref") or ""), 40) or None})
    return validos, descartes


def validar_seleccion(sel, necesidad, agente, flujo, autorizado, dinamica_bloqueada) -> str | None:
    """None si la elección es aceptable; si no, el motivo del rechazo."""
    if not isinstance(sel, dict) or not isinstance(sel.get("herramienta"), str):
        return "la salida no es {herramienta: nombre}"
    h = herramientas.REGISTRO.get(sel["herramienta"])
    if h is None:
        return f"herramienta inexistente en el registro: {sel['herramienta'][:40]}"
    if h.nombre not in NECESIDADES.get(necesidad, ()):
        return f"{h.nombre} no sirve para la necesidad {necesidad}"
    if agente not in h.agentes:
        return f"{h.nombre} no está permitida para {agente}"
    if flujo not in h.contextos:
        return f"{h.nombre} no existe en el flujo {flujo}"
    if h.requiere_autorizacion and not autorizado:
        return f"{h.nombre} requiere una autorización que el usuario no dio"
    if h.ejecuta_codigo and dinamica_bloqueada:
        return f"{h.nombre} ejecuta código y la ejecución dinámica está bloqueada"
    return None


def validar_diagnosticos(lista, archivos) -> tuple:
    validos, descartes = [], []
    if not isinstance(lista, list):
        return [], [{"motivo": "la salida no es una lista"}]
    lineas = {r: t.count("\n") + 1 for r, t in (archivos or {}).items() if isinstance(t, str)}
    for i, d in enumerate(lista):
        if len(validos) >= MAX_DIAGNOSTICOS:
            descartes.append({"i": i, "motivo": f"más de {MAX_DIAGNOSTICOS} diagnósticos"})
            continue
        if not isinstance(d, dict) or not isinstance(d.get("causa"), str) or not isinstance(d.get("propuesta"), str):
            descartes.append({"i": i, "motivo": "faltan causa o propuesta (texto)"})
            continue
        if d.get("confianza") not in CONFIANZAS:
            descartes.append({"i": i, "motivo": "confianza no admitida (baja|media|alta)"})
            continue
        arch = d.get("archivo")
        if arch is not None and arch not in lineas:
            descartes.append({"i": i, "motivo": "cita un archivo que no existe en la versión"})
            continue
        lin = d.get("linea")
        if lin is not None and (not isinstance(lin, int) or isinstance(lin, bool) or lin < 1
                                or (arch is not None and lin > lineas[arch])):
            descartes.append({"i": i, "motivo": "línea fuera del archivo"})
            continue
        causa, prop = sanea.limpiar(d["causa"], MAX_CAMPO), sanea.limpiar(d["propuesta"], MAX_CAMPO)
        v = aprendizaje.analizar_contenido(causa + "\n" + prop)
        if v["veredicto"] != "aceptado":
            descartes.append({"i": i, "motivo": f"contenido {v['veredicto']}"})
            continue
        validos.append({"causa": causa, "archivo": arch, "linea": lin, "propuesta": prop, "confianza": d["confianza"]})
    return validos, descartes


# --- capa que usa el controlador -----------------------------------------------------------------------------------
class Componentes:
    """Punto ÚNICO por el que funcion_supervisada usa memoria, selector y diagnóstico. Toda salida se valida."""

    def __init__(self, recuperador=None, selector=None, diagnostico=None, memoria=None, tarea_ref=None):
        self._mem = memoria
        self.por_defecto = {"recuperador": RecuperadorExperiencias(memoria, tarea_ref), "selector": SelectorRegistro(),
                            "diagnostico": DiagnosticoEstatico()}
        self.activos = {"recuperador": recuperador or self.por_defecto["recuperador"],
                        "selector": selector or self.por_defecto["selector"],
                        "diagnostico": diagnostico or self.por_defecto["diagnostico"]}
        self.externos = {k for k, v in (("recuperador", recuperador), ("selector", selector),
                                        ("diagnostico", diagnostico)) if v is not None}
        self.incidencias = []

    def _nota(self, componente, motivo, **datos):
        self.incidencias.append({"componente": componente,
                                 "nombre": str(getattr(self.activos[componente], "nombre", "?"))[:40],
                                 "motivo": str(motivo)[:200], **datos})

    def _llamar(self, componente, metodo, *args):
        """(salida, origen). Si el componente externo falla, se usa el de por defecto (y se registra)."""
        obj = self.activos[componente]
        try:
            return getattr(obj, metodo)(*args), ("externo" if componente in self.externos else "por_defecto")
        except Exception as e:                                 # un componente roto no detiene la tarea
            self._nota(componente, f"excepción: {type(e).__name__}: {str(e)[:120]}")
            if componente not in self.externos:
                return None, "fallo"
            try:
                return getattr(self.por_defecto[componente], metodo)(*args), "por_defecto_tras_fallo"
            except Exception as e2:
                self._nota(componente, f"el de por defecto también falló: {type(e2).__name__}")
                return None, "fallo"

    # memoria -------------------------------------------------------------------------------------------------
    def memoria(self, agente, consulta, n=2) -> dict:
        crudo, origen = self._llamar("recuperador", "recuperar", agente, sanea.limpiar(consulta, 400), int(n))
        validos, desc = validar_recuerdos(crudo if crudo is not None else [], n)
        for d in desc:
            self._nota("recuperador", "descartado: " + d["motivo"], agente=agente)
        cal = ""
        if self._mem is not None:
            try:
                cal = self._mem.linea_calibracion(agente)
            except Exception as e:
                self._nota("recuperador", f"calibración no disponible: {type(e).__name__}")
        lineas = [aprendizaje.formatear_para_prompt(m) for m in validos]
        if origen.startswith("externo") or origen == "por_defecto_tras_fallo":
            lineas = [l.replace("- [", f"- [origen={origen}:{self._nombre('recuperador')} | ", 1) for l in lineas]
        texto = "" if not (lineas or cal) else "\n".join(
            [autocorreccion_aviso()] + ([cal] if cal else []) + lineas)
        return {"texto": texto, "items": validos, "descartados": len(desc), "origen": origen}

    # herramientas ----------------------------------------------------------------------------------------------
    def herramienta(self, necesidad, agente="controlador", flujo="motor", autorizado=False,
                    dinamica_bloqueada=True) -> dict:
        if necesidad not in NECESIDADES:
            raise ValueError(f"necesidad desconocida: {necesidad}")
        ctx = {"agente": agente, "flujo": flujo, "autorizado": bool(autorizado),
               "ejecucion_dinamica": "bloqueada" if dinamica_bloqueada else "permitida",
               "candidatas": [h for h in NECESIDADES[necesidad] if h in herramientas.REGISTRO]}
        crudo, origen = self._llamar("selector", "seleccionar", necesidad, dict(ctx))
        motivo = validar_seleccion(crudo, necesidad, agente, flujo, autorizado, dinamica_bloqueada)
        rechazada = motivo is not None
        if rechazada:
            self._nota("selector", "elección rechazada: " + motivo, necesidad=necesidad)
            crudo = {"herramienta": None, "motivo": None}
            for nombre in NECESIDADES[necesidad]:                  # elección determinista y segura por defecto
                if validar_seleccion({"herramienta": nombre}, necesidad, agente, flujo, autorizado,
                                     dinamica_bloqueada) is None:
                    crudo = {"herramienta": nombre, "motivo": "elección por defecto tras rechazar la del selector"}
                    break
        h = crudo.get("herramienta")
        return {"necesidad": necesidad, "herramienta": h, "principal": NECESIDADES[necesidad][0],
                "sustituida": h != NECESIDADES[necesidad][0], "rechazada": rechazada, "motivo_rechazo": motivo,
                "motivo": sanea.limpiar(str(crudo.get("motivo") or ""), 160), "origen": origen,
                "ejecuta_codigo": bool(h and herramientas.REGISTRO[h].ejecuta_codigo)}

    # diagnóstico -----------------------------------------------------------------------------------------------
    def diagnostico(self, errores, archivos) -> dict:
        copia_err = [{k: e.get(k) for k in ("tipo", "archivo", "linea", "detalle", "nombre", "modulo")} for e in errores]
        crudo, origen = self._llamar("diagnostico", "diagnosticar", copia_err, dict(archivos or {}))
        validos, desc = validar_diagnosticos(crudo if crudo is not None else [], archivos)
        for d in desc:
            self._nota("diagnostico", "descartado: " + d["motivo"])
        return {"items": validos, "descartados": len(desc), "origen": origen, "nombre": self._nombre("diagnostico")}

    def _nombre(self, componente):
        return sanea.limpiar(str(getattr(self.activos[componente], "nombre", "?")), 40)

    def describir(self) -> dict:
        return {"version_interfaz": VERSION_INTERFAZ,
                **{k: {"nombre": self._nombre(k), "origen": "externo" if k in self.externos else "por_defecto"}
                   for k in self.activos},
                "incidencias": list(self.incidencias)}


def autocorreccion_aviso() -> str:
    """El mismo aviso de datos no confiables que usa la memoria de equipo de V2-F."""
    from . import experiencias
    return experiencias.AVISO


# --- conformidad ---------------------------------------------------------------------------------------------------
_SONDAS = {
    "recuperador": ("A1", "función mediana lista vacía", 2),
    "selector": ("comprobar_sintaxis", {"agente": "controlador", "flujo": "motor", "autorizado": False,
                                        "ejecucion_dinamica": "bloqueada", "candidatas": ["analisis_estatico"]}),
    "diagnostico": ([{"tipo": "sintaxis", "archivo": "solucion.py", "linea": 1, "detalle": "invalid syntax"}],
                    {"solucion.py": "def f(:\n    pass\n"}),
}


def comprobar_conformidad(obj, componente) -> list:
    """Problemas de `obj` frente al contrato `componente` (recuperador|selector|diagnostico). Lista vacía = conforme.
    Llama UNA vez al componente con una entrada de sonda y valida su salida con las mismas reglas que en uso."""
    if componente not in CONTRATOS:
        raise ValueError(f"componente desconocido: {componente}")
    proto, metodo, aridad = CONTRATOS[componente]
    prob = []
    if not isinstance(getattr(obj, "nombre", None), str) or not getattr(obj, "nombre").strip():
        prob.append("falta el atributo «nombre» (texto)")
    f = getattr(obj, metodo, None)
    if not callable(f):
        return prob + [f"falta el método {metodo}()"]
    try:
        params = [p for p in inspect.signature(f).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if len(params) < aridad and not any(p.kind == p.VAR_POSITIONAL for p in inspect.signature(f).parameters.values()):
            prob.append(f"{metodo}() debe aceptar {aridad} argumentos")
    except (TypeError, ValueError):
        prob.append(f"no se puede leer la firma de {metodo}()")
    if not isinstance(obj, proto):
        prob.append(f"no cumple el protocolo {proto.__name__}")
    if prob:
        return prob
    try:
        salida = f(*_SONDAS[componente])
    except Exception as e:
        return [f"la sonda lanzó {type(e).__name__}: {str(e)[:120]}"]
    if componente == "recuperador":
        _, desc = validar_recuerdos(salida, 2)
        prob += [f"salida de sonda: {d['motivo']}" for d in desc if d["motivo"].startswith(("la salida", "recuerdo sin",
                                                                                              "tipo", "fuente", "estado"))]
    elif componente == "selector":
        m = validar_seleccion(salida, "comprobar_sintaxis", "controlador", "motor", False, True)
        if m:
            prob.append(f"salida de sonda: {m}")
    else:
        _, desc = validar_diagnosticos(salida, _SONDAS["diagnostico"][1])
        prob += [f"salida de sonda: {d['motivo']}" for d in desc]
    return prob
