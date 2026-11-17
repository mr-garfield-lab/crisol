"""V2-F: REGISTRO TIPADO de herramientas, validación de solicitudes y despachador con errores clasificados.

Qué resuelve (frente a V2-E.7): cada flujo decidía por su cuenta qué herramienta usar y los errores llegaban
como texto suelto. Aquí hay una sola LISTA BLANCA inmutable y un único camino de ejecución:

  * REGISTRO (MappingProxyType de dataclasses congeladas): nombre, agentes que pueden pedirla, si exige la
    autorización del usuario, si ejecuta código, tipo de argumento y sustituta. Ningún texto de agente, recuerdo,
    plan ni tarea puede añadir herramientas ni cambiar permisos: el registro no tiene métodos de escritura y las
    pruebas comprueban que sigue igual tras las ejecuciones.
  * El DESPACHADOR aplica el registro en cada uso (agente y flujo permitidos) y valida el argumento ANTES de
    ejecutar nada. Los agentes piden la ejecución de casos con líneas «CASO: f(<literales>) == <literal>»: un formato
    estricto que el controlador convierte en la prueba (casos.py).
  * Errores con CATEGORÍA (ver CATEGORIAS): el agente recibe en su siguiente prompt por qué se rechazó su
    solicitud, y las estadísticas por agente van a su memoria (aprenden a usar las herramientas sin ampliar nada).
  * Sustitución explícita: si no hay autorización para ejecutar pruebas, se ofrece el análisis estático marcado
    «sustituida: no es una prueba real». Nunca al revés.
  * Ninguna herramienta abre red, instala nada ni escribe fuera del laboratorio; las que ejecutan código usan el
    EJECUTOR RESTRINGIDO de V2-E.7 (lista blanca AST + proceso limitado + gancho de auditoría; NO es un sandbox).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType

from . import analisis_estatico, casos as C, ejecutor_restringido, sanea
from .ejecutor import Politica

ESTADOS = ("ok", "fallos", "rechazada", "no_autorizada", "error", "sustituida")
CATEGORIAS = {
    "herramienta_desconocida": "la herramienta no existe en el registro",
    "no_permitida_para_agente": "ese agente no puede pedir esa herramienta",
    "no_permitida_en_este_paso": "la herramienta no está disponible en este paso",
    "argumento_invalido": "el argumento no tiene el formato esperado",
    "limite_solicitudes": "se superó el número de solicitudes del paso",
    "no_autorizada": "el usuario no autorizó ejecutar pruebas (--autorizo-pruebas)",
    "rechazada_lista_blanca": "el código no pasó la lista blanca del ejecutor restringido",
    "tiempo_excedido": "la ejecución superó su tiempo límite",
    "sin_resultado_valido": "la ejecución no devolvió un resultado con el nonce correcto",
    "error_herramienta": "la herramienta falló (error registrado)",
}


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    agentes: tuple
    requiere_autorizacion: bool
    ejecuta_codigo: bool
    argumento: str                   # ninguno | archivo_py | casos | candidato
    contextos: tuple                 # flujos donde existe
    sustituta: str | None = None


REGISTRO = MappingProxyType({
    "analisis_estatico": Herramienta(
        "analisis_estatico", "ast.parse del código: sintaxis, nombres importados, imports y llamadas de riesgo. "
        "NO ejecuta nada y NO es una prueba.", ("A1", "A2", "A3", "controlador"), False, False, "archivo_py",
        ("motor", "debate", "banco")),
    "pruebas_python": Herramienta(
        "pruebas_python", "ejecuta los test_*.py del proyecto con el ejecutor restringido",
        ("A2", "controlador"), True, True, "ninguno", ("motor",), "analisis_estatico"),
    "ejecutar_casos": Herramienta(
        "ejecutar_casos", "ejecuta CASOS literales (f(args) == valor / lanza X) contra una solución con el "
        "ejecutor restringido; la prueba la escribe el controlador", ("A1", "A2", "A3", "controlador", "evaluador"),
        True, True, "casos", ("motor", "debate", "banco"), "analisis_estatico"),
    # PZ ModLab: las operaciones del contrato de V2-E.7-r2. Se ejecutan SOLO por su camino existente
    # (tareas._ejecutar_pz -> modlab_pz_adaptador); aquí se declaran para que la lista blanca sea una sola.
    "simular_escenario": Herramienta("simular_escenario", "PZ ModLab: simulación declarativa (no es el juego)",
                                     ("A2",), True, False, "archivo_json", ("modlab_pz",)),
    "analizar_lua_estatico": Herramienta("analizar_lua_estatico", "PZ ModLab: patrones en Lua (no lo ejecuta)",
                                         ("A2",), True, False, "archivo_lua", ("modlab_pz",)),
    "inspeccionar_zip": Herramienta("inspeccionar_zip", "PZ ModLab: lista y hashea un ZIP (no extrae)",
                                    ("A2",), True, False, "archivo_zip", ("modlab_pz",)),
})
def disponibles(agente: str, contexto: str, autorizado: bool) -> list:
    """Herramientas que `agente` puede pedir en `contexto` con la autorización actual (para el prompt: solo se
    anuncian las que de verdad se pueden usar)."""
    out = []
    for h in REGISTRO.values():
        if agente in h.agentes and contexto in h.contextos and (autorizado or not h.requiere_autorizacion):
            out.append(h.nombre)
    return out


def seleccionar(necesidad: str, autorizado: bool) -> dict:
    """Selección DETERMINISTA de la herramienta para una necesidad del controlador.
    necesidad: comprobar_comportamiento | comprobar_sintaxis | ejecutar_casos."""
    tabla = {"comprobar_comportamiento": "pruebas_python", "ejecutar_casos": "ejecutar_casos",
             "comprobar_sintaxis": "analisis_estatico"}
    if necesidad not in tabla:
        raise ValueError(f"necesidad desconocida: {necesidad}")
    h = REGISTRO[tabla[necesidad]]
    if h.requiere_autorizacion and not autorizado:
        return {"herramienta": h.sustituta, "sustituida": True, "motivo": CATEGORIAS["no_autorizada"],
                "nota": "sustituida por análisis estático: NO es una prueba real"}
    return {"herramienta": h.nombre, "sustituida": False, "motivo": None, "nota": None}


def retroalimentacion(rechazos_casos=()) -> str:
    """Texto breve para el SIGUIENTE prompt del agente: qué CASO se rechazó y por qué (aprende a usar el formato)."""
    return "\n".join(f"- CASO rechazado ({r['motivo']}): {r['linea'][:80]}" for r in list(rechazos_casos)[:6])


class Despachador:
    """Ejecuta herramientas del registro. Todo resultado lleva su categoría y queda en un registro JSONL.

    lab, partes_base: dónde guarda el ejecutor restringido (pruebas/P<nnn>/) y el registro herramientas.jsonl.
    autorizado: la autorización EXPLÍCITA del usuario para ejecutar pruebas (nunca viene de un agente)."""

    def __init__(self, lab, partes_base=(), autorizado=False, ahora=None, seg=None, contexto="motor"):
        if contexto not in {c for h in REGISTRO.values() for c in h.contextos}:
            raise ValueError(f"contexto de herramientas desconocido: {contexto}")
        self.contexto = contexto
        self.lab, self.partes_base = lab, tuple(partes_base)
        self.ahora = ahora
        self.seg = seg
        # La autorización vive SOLO en el ejecutor restringido (una única fuente; la concede la CLI del usuario).
        self.ejecutor = ejecutor_restringido.EjecutorRestringido(lab, self.partes_base, autorizado=autorizado is True,
                                                                 ahora=ahora, seg=seg)
        self.registro = []
        self.estadisticas = {}                 # {agente: {estado/categoria: n}}

    @property
    def permitido(self) -> bool:
        """¿Autorizó el usuario ejecutar pruebas? (lectura del ejecutor; aquí no se puede cambiar)."""
        return self.ejecutor.autorizado is True

    # --- registro --------------------------------------------------------------------------------
    def _anotar(self, agente, herramienta, estado, categoria=None, **datos):
        if estado not in ESTADOS:
            raise ValueError("estado de herramienta desconocido")
        e = {"n": len(self.registro) + 1, "agente": agente, "herramienta": herramienta, "estado": estado,
             "categoria": categoria, **datos}
        self.registro.append(e)
        st = self.estadisticas.setdefault(agente, {})
        st[estado] = st.get(estado, 0) + 1
        if categoria:
            st[categoria] = st.get(categoria, 0) + 1
        try:
            if self.partes_base:
                self.lab.crear_dir(*self.partes_base)
            self.lab.anexar(self.partes_base + ("herramientas.jsonl",),
                            json.dumps(e, ensure_ascii=False, default=str) + "\n")
        except (OSError, ValueError):
            pass
        return e

    def _permitida(self, nombre, agente):
        """Categoría de rechazo según el REGISTRO (None si se puede usar aquí y por este agente)."""
        h = REGISTRO.get(nombre)
        if h is None:
            return "herramienta_desconocida"
        if agente not in h.agentes:
            return "no_permitida_para_agente"
        if self.contexto not in h.contextos:
            return "no_permitida_en_este_paso"
        return None

    def _rechazo(self, nombre, agente, categoria, **base):
        self._anotar(agente, nombre, "rechazada", categoria)
        return dict(base, estado="rechazada", categoria=categoria, tipo=None, errores=[CATEGORIAS[categoria]])

    # --- herramientas -----------------------------------------------------------------------------
    def analisis_estatico(self, archivos: dict, agente="controlador", solo_codigo=False) -> dict:
        cat = self._permitida("analisis_estatico", agente)
        if cat:
            return self._rechazo("analisis_estatico", agente, cat, errores_analisis=[], avisos=[])
        a = analisis_estatico.analizar(dict(archivos))
        errores = a["errores"]
        if solo_codigo:            # código sin pruebas todavía: las ausencias de test_*.py no son errores
            errores = [e for e in errores if e["tipo"] not in ("sin_archivo_de_pruebas", "pruebas_ausentes")]
        estado = "fallos" if errores else "ok"
        self._anotar(agente, "analisis_estatico", estado, None, errores=len(errores))
        return {"estado": estado, "tipo": "estatico", "errores": errores, "avisos": a["avisos"],
                "nota": "análisis estático: no es una prueba"}

    def pruebas_python(self, archivos: dict, agente="controlador") -> dict:
        cat = self._permitida("pruebas_python", agente)
        if cat:
            return self._rechazo("pruebas_python", agente, cat)
        if not self.permitido:
            sel = seleccionar("comprobar_comportamiento", False)
            r = self.analisis_estatico(archivos, agente)
            self._anotar(agente, "pruebas_python", "sustituida", "no_autorizada", sustituta=sel["herramienta"])
            return dict(r, sustituida=True, nota=sel["nota"])
        res = self.ejecutor.ejecutar(_Espacio(archivos), "pruebas_python", Politica()).a_dict()
        cat = _categoria_resultado(res)
        self._anotar(agente, "pruebas_python", "ok" if res["estado"] == "ok" else
                     ("rechazada" if cat == "rechazada_lista_blanca" else "fallos" if res["estado"] == "fallos" else "error"),
                     cat, carpeta=(res.get("detalle") or {}).get("carpeta"))
        return dict(res, categoria=cat)

    def ejecutar_casos(self, archivos_solucion: dict, casos, propiedades=(), agente="controlador",
                       etiqueta="casos") -> dict:
        """Ejecuta `casos` (casos.Caso) contra la solución {ruta: contenido}. Devuelve
        {estado, categoria, por_caso: {id: {estado: pasa|falla|error|no_ejecutado, obtenido, prueba, tipo}},
         propiedades: {...}, carpeta, omitidos}. Nunca inventa un resultado: sin autorización, nada se ejecuta."""
        casos = list(casos)
        base = {"por_caso": {c.id: {"estado": "no_ejecutado", "obtenido": None, "prueba": None, "tipo": "caso"}
                             for c in casos}, "propiedades": {}, "carpeta": None, "omitidos": []}
        cat = self._permitida("ejecutar_casos", agente)
        if cat:
            return self._rechazo("ejecutar_casos", agente, cat, **base)
        if not casos:
            return dict(base, estado="ok", categoria=None)
        if not self.permitido:
            self._anotar(agente, "ejecutar_casos", "no_autorizada", "no_autorizada", n=len(casos))
            return dict(base, estado="no_autorizada", categoria="no_autorizada")
        modulos = C.funciones_definidas(archivos_solucion)
        gen = C.generar_modulo(casos, modulos, propiedades)
        nombre = "test_" + re.sub(r"[^a-z0-9_]", "_", etiqueta.lower())[:30] + "_v2f.py"
        espacio = {r: t for r, t in archivos_solucion.items() if not r.rsplit("/", 1)[-1].startswith("test")}
        for o in gen["omitidos"]:
            base["por_caso"][o["caso"]].update(estado="no_ejecutado", obtenido=o["motivo"])
        base["omitidos"] = gen["omitidos"]
        if not gen["pruebas"]:
            self._anotar(agente, "ejecutar_casos", "fallos", "argumento_invalido", motivo="ningún caso ejecutable")
            return dict(base, estado="fallos", categoria="argumento_invalido")
        espacio[nombre] = gen["texto"]
        res = self.ejecutor.ejecutar(_Espacio(espacio), "pruebas_python", Politica()).a_dict()
        det = res.get("detalle") or {}
        cat = _categoria_resultado(res)
        base["carpeta"] = det.get("carpeta")
        pr = det.get("pruebas") or {}
        obtenidos = {}
        if det.get("carpeta") and res.get("tipo") == "real":
            txt = self.lab.leer_texto(self.partes_base + tuple(det["carpeta"].split("/")) + ("informe_unittest.txt",),
                                      400_000) or ""
            obtenidos = C.obtenidos_de_informe(txt)
        for prueba, info in gen["pruebas"].items():
            if res.get("tipo") != "real":
                estado = "no_ejecutado"
                obt = "; ".join(det.get("errores") or [])[:300] or res.get("salida", "")[:300]
            elif prueba in pr:
                estado = "pasa" if pr[prueba] == "ok" else "falla"
                obt = obtenidos.get(prueba)
            else:
                estado = "error"
                obt = "; ".join(det.get("errores") or [])[:300] or "la prueba no llegó a ejecutarse"
            if info["tipo"] == "caso":
                base["por_caso"][info["caso"]] = {"estado": estado, "obtenido": obt, "prueba": prueba, "tipo": "caso"}
            else:
                base["propiedades"].setdefault(info["caso"], {})[info["tipo"]] = {"estado": estado, "obtenido": obt,
                                                                                  "prueba": prueba}
        estado_global = "ok" if res["estado"] == "ok" else ("rechazada" if cat == "rechazada_lista_blanca" else
                                                            "fallos" if res["estado"] == "fallos" else "error")
        self._anotar(agente, "ejecutar_casos", estado_global, cat, carpeta=det.get("carpeta"), n=len(casos),
                     pasan=sum(1 for v in base["por_caso"].values() if v["estado"] == "pasa"))
        return dict(base, estado=estado_global, categoria=cat, tipo=res.get("tipo"),
                    errores=(det.get("errores") or [])[:10])


class _Espacio:
    def __init__(self, archivos):
        self.archivos = dict(archivos)


def _categoria_resultado(res: dict):
    det = res.get("detalle") or {}
    if det.get("rechazado_por_politica"):
        return "rechazada_lista_blanca"
    if res.get("estado") == "no_disponible":
        return "no_autorizada"
    if res.get("tipo") == "real" and det.get("nonce_valido") is False:
        return "sin_resultado_valido"
    if res.get("tipo") == "real" and "TIEMPO EXCEDIDO" in (res.get("salida") or ""):
        return "tiempo_excedido"
    if res.get("estado") == "error":
        return "error_herramienta"
    return None


def huella_registro() -> str:
    """Huella del registro (para comprobar que nada lo ha cambiado durante una ejecución)."""
    d = {k: [h.nombre, h.agentes, h.requiere_autorizacion, h.ejecuta_codigo, h.argumento, h.contextos, h.sustituta]
         for k, h in sorted(REGISTRO.items())}
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def coherente_con_modlab(contrato_ops) -> bool:
    """Las herramientas modlab del registro son EXACTAMENTE las operaciones permitidas del contrato de ModLab."""
    propias = {n for n, h in REGISTRO.items() if "modlab_pz" in h.contextos}
    return propias == set(contrato_ops)

