"""Equipo IA V3 · PROGRAMACIÓN CONTROLADA (Etapa 3): PROPUESTA → AUTORIZACIÓN → APLICACIÓN.

Para modificar archivos Python de proyectos del laboratorio (`<lab>/proyectos_v3/<proyecto>/`):

1. **Los agentes (A1/A2/A3) solo proponen.** Usan las herramientas de un REGISTRO congelado: `leer`, `listar`,
   `buscar` y `proponer`. Ninguna herramienta de agente escribe archivos, autoriza ni ejecuta código; una
   solicitud fuera del registro, de un agente no permitido o con argumentos inválidos se rechaza con su
   categoría.
2. **Solo el USUARIO autoriza**, por la orden de línea de comandos, tecleando el principio (al menos 12
   caracteres) del SHA-256 del contenido propuesto.
   - La autorización es de UN solo uso, caduca y vale solo para esa propuesta y ese archivo.
   - No se autoriza una propuesta con errores de sintaxis.
   - Si el análisis estático (`eq2.analisis_estatico`) da avisos de riesgo, hay que aceptarlos explícitamente.
3. **Solo el CONTROLADOR aplica.**
   - Comprueba la autorización y que el archivo siga con el SHA-256 con el que se propuso (contra el TOCTOU:
     nunca se escribe sobre una versión distinta de la revisada).
   - Escribe de forma atómica (temporal + `os.replace`) y comprueba el resultado.
   - Cada intento rechazado también queda registrado.
4. **Ejecutar código generado sigue DESHABILITADO (SEG-01).** La herramienta `ejecutar_pruebas` devuelve
   siempre «no_disponible».

Todo se guarda en `<lab>/cambios_v3.sqlite3`: solo añadir, con cadena de hashes (`eq3.almacen`).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from . import almacen as A
from . import ingesta as I
from .plataforma import es_enlace

MAX_CONTENIDO = 256 * 1024
MIN_PREFIJO_SHA = 12
RE_PROYECTO = re.compile(r"[a-z0-9_]{1,40}")
RE_PROPUESTA = re.compile(r"PROP-\d{4,6}")
NO_DISPONIBLE = ("no_disponible", "SEG-01: no hay aislamiento del sistema operativo verificable; el código "
                 "generado no se ejecuta")


class ErrorCambio(Exception):
    """Operación rechazada (queda registrada cuando hay una propuesta a la que asociarla)."""


class Cambios(A.Almacen):
    NOMBRE = "cambios"
    ESQUEMA_VERSION = "1"
    TABLAS = {
        "proyectos": ("id", "ruta", "creado"),
        "propuestas": ("id", "n", "proyecto_id", "agente", "archivo", "sha256_antes", "sha256_despues", "contenido",
                       "diff", "analisis", "autorizable", "motivo", "origen", "ts"),
        "autorizaciones": ("id", "propuesta_id", "actor", "sha256_despues", "avisos_aceptados", "caduca", "ts"),
        "aplicaciones": ("id", "propuesta_id", "autorizacion_id", "sha256_resultado", "ts"),
        "rechazos": ("id", "propuesta_id", "operacion", "motivo", "ts"),
    }
    ESQUEMA = """
CREATE TABLE proyectos (id TEXT PRIMARY KEY, ruta TEXT NOT NULL, creado TEXT NOT NULL);
CREATE TABLE propuestas (id TEXT PRIMARY KEY, n INTEGER NOT NULL UNIQUE,
  proyecto_id TEXT NOT NULL REFERENCES proyectos(id), agente TEXT NOT NULL CHECK (agente IN ('A1', 'A2', 'A3')),
  archivo TEXT NOT NULL, sha256_antes TEXT, sha256_despues TEXT NOT NULL, contenido TEXT NOT NULL,
  diff TEXT NOT NULL, analisis TEXT NOT NULL, autorizable INTEGER NOT NULL CHECK (autorizable IN (0, 1)),
  motivo TEXT, origen TEXT, ts TEXT NOT NULL);
CREATE TABLE autorizaciones (id TEXT PRIMARY KEY, propuesta_id TEXT NOT NULL UNIQUE REFERENCES propuestas(id),
  actor TEXT NOT NULL CHECK (actor = 'usuario'), sha256_despues TEXT NOT NULL,
  avisos_aceptados INTEGER NOT NULL CHECK (avisos_aceptados IN (0, 1)), caduca TEXT NOT NULL, ts TEXT NOT NULL);
CREATE TABLE aplicaciones (id TEXT PRIMARY KEY, propuesta_id TEXT NOT NULL UNIQUE REFERENCES propuestas(id),
  autorizacion_id TEXT NOT NULL UNIQUE REFERENCES autorizaciones(id), sha256_resultado TEXT NOT NULL,
  ts TEXT NOT NULL);
CREATE TABLE rechazos (id TEXT PRIMARY KEY, propuesta_id TEXT NOT NULL REFERENCES propuestas(id),
  operacion TEXT NOT NULL CHECK (operacion IN ('autorizar', 'aplicar')), motivo TEXT NOT NULL, ts TEXT NOT NULL);
"""


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    agentes: frozenset
    efecto: str                      # «lectura», «propuesta» o «ninguno»; ninguna escribe ni ejecuta
    args: tuple                      # ((nombre, longitud_máxima), ...); todos los argumentos son texto


_TODOS = frozenset({"A1", "A2", "A3"})
REGISTRO = MappingProxyType({h.nombre: h for h in (
    Herramienta("leer", _TODOS, "lectura", (("ruta", 512),)),
    Herramienta("listar", _TODOS, "lectura", (("ruta", 512),)),
    Herramienta("buscar", _TODOS, "lectura", (("consulta", 2048),)),
    Herramienta("proponer", frozenset({"A1", "A2"}), "propuesta",
                (("archivo", 512), ("contenido", MAX_CONTENIDO), ("motivo", 2048))),
    Herramienta("ejecutar_pruebas", frozenset({"A2"}), "ninguno", ()),
)})


def huella_registro() -> str:
    return A.sha256_texto(A.canonico({n: [sorted(h.agentes), h.efecto, [list(a) for a in h.args]]
                                      for n, h in sorted(REGISTRO.items())}))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _rel_segura(rel: str) -> str:
    p = PurePosixPath(rel)
    # «:» (2026-11-18, revisión de seguridad): en Windows «C:/Windows» no es absoluta para PurePosixPath, pero al unirla a
    # una ruta de Windows salta a esa unidad; «x:y» también abriría un flujo alternativo de NTFS.
    if not p.parts or p.is_absolute() or ".." in p.parts or "\\" in rel or ":" in rel or rel.startswith("."):
        raise ErrorCambio(f"ruta no permitida: {rel!r}")
    return p.as_posix()


def _dentro(raiz: Path, rel: str) -> Path:
    """La ruta del proyecto para `rel`, comprobando cada componente (sin enlaces ni uniones de Windows en NINGÚN tramo)
    y que el destino resuelto sigue dentro de `raiz` (segunda barrera, por si la primera se queda corta)."""
    actual = raiz
    for parte in PurePosixPath(_rel_segura(rel)).parts:
        actual = actual / parte
        if es_enlace(actual):
            raise ErrorCambio(f"enlace no permitido en la ruta: {rel!r}")
    if not actual.resolve().is_relative_to(raiz.resolve()):
        raise ErrorCambio(f"la ruta sale del proyecto: {rel!r}")
    return actual


class Controlador:
    """Único componente que aplica cambios. Los agentes llegan por `solicitar()`; el usuario, por la CLI."""

    def __init__(self, lab: Path, ruta_db: Path | None = None, reloj=None):
        self.lab = Path(lab).resolve()
        self.cambios = Cambios(ruta_db or self.lab / "cambios_v3.sqlite3")
        self.reloj = reloj or (lambda: datetime.now(timezone.utc).replace(microsecond=0))

    def cerrar(self):
        self.cambios.cerrar()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()

    # --- proyectos y rutas ---------------------------------------------------------------------------------
    def _rel_proyecto(self, proyecto: str) -> str:
        if not RE_PROYECTO.fullmatch(proyecto or ""):
            raise ErrorCambio(f"nombre de proyecto no permitido: {proyecto!r}")
        return f"proyectos_v3/{proyecto}"

    def proyecto(self, proyecto: str) -> Path:
        rel = self._rel_proyecto(proyecto)
        raiz = self.lab / rel
        for p in (self.lab / "proyectos_v3", raiz):
            if es_enlace(p):
                raise ErrorCambio(f"enlace simbólico no permitido: {p}")
        raiz.mkdir(parents=True, exist_ok=True)
        if not self.cambios.existe("proyectos", id=proyecto):
            with self.cambios.transaccion():
                self.cambios.insertar("proyectos", {"id": proyecto, "ruta": rel, "creado": A.ahora()})
        return raiz

    def _sha_actual(self, proyecto: str, archivo: str):
        """SHA-256 del archivo del proyecto, o None si no existe. Rechaza enlaces simbólicos en cualquier tramo."""
        rel = f"{self._rel_proyecto(proyecto)}/{_rel_segura(archivo)}"
        try:
            return _sha(I.leer(self.lab, rel, MAX_CONTENIDO))
        except I.ErrorValidacion as e:
            if str(e).startswith("no existe"):
                return None
            raise ErrorCambio(str(e)) from None

    # --- herramientas de los agentes -----------------------------------------------------------------------
    def solicitar(self, proyecto: str, solicitud) -> dict:
        """Única entrada de los agentes. Nunca lanza: devuelve {estado, ...} con la categoría del rechazo."""
        if not isinstance(solicitud, dict) or set(solicitud) != {"agente", "herramienta", "args"}:
            return {"estado": "rechazada", "categoria": "formato", "motivo": "se espera {agente, herramienta, args}"}
        h = REGISTRO.get(solicitud["herramienta"]) if isinstance(solicitud["herramienta"], str) else None
        if h is None:
            return {"estado": "rechazada", "categoria": "herramienta_desconocida",
                    "motivo": f"no está en el registro: {solicitud['herramienta']!r}"}
        if solicitud["agente"] not in h.agentes:
            return {"estado": "rechazada", "categoria": "agente_no_permitido",
                    "motivo": f"{solicitud['agente']!r} no puede usar {h.nombre}"}
        args = solicitud["args"]
        if not isinstance(args, dict) or set(args) != {a for a, _ in h.args} or any(
                not isinstance(args[a], str) or len(args[a]) > maximo for a, maximo in h.args):
            return {"estado": "rechazada", "categoria": "argumentos", "motivo": f"argumentos de {h.nombre}: "
                    + ", ".join(f"{a} (texto ≤ {m})" for a, m in h.args)}
        try:
            return self._despachar(proyecto, solicitud["agente"], h.nombre, args)
        except (ErrorCambio, I.ErrorValidacion) as e:
            return {"estado": "rechazada", "categoria": "validacion", "motivo": str(e)[:300]}

    def _despachar(self, proyecto, agente, nombre, args) -> dict:
        raiz = self.proyecto(proyecto)
        if nombre == "ejecutar_pruebas":
            return {"estado": NO_DISPONIBLE[0], "motivo": NO_DISPONIBLE[1]}
        if nombre == "leer":
            texto = I.leer(self.lab, f"{self._rel_proyecto(proyecto)}/{_rel_segura(args['ruta'])}", MAX_CONTENIDO)
            return {"estado": "ok", "contenido": texto.decode("utf-8", "replace"), "sha256": _sha(texto)}
        if nombre == "listar":
            base = raiz if args["ruta"] in ("", ".") else _dentro(raiz, args["ruta"])
            if es_enlace(base) or not base.is_dir():
                raise ErrorCambio(f"no es una carpeta del proyecto: {args['ruta']!r}")
            return {"estado": "ok", "entradas": sorted(p.name + ("/" if p.is_dir() else "") for p in base.iterdir()
                                                       if not es_enlace(p))}
        if nombre == "buscar":
            from . import grafo as G
            indices = self.lab / "indices_v3"
            indices.mkdir(exist_ok=True)
            with G.Grafo(indices / f"{proyecto}.sqlite3") as g:
                g.indexar(raiz)
                return {"estado": "ok", "resultados": g.recuperar(args["consulta"], 8)}
        return self.proponer(proyecto, agente, args["archivo"], args["contenido"], args["motivo"])

    # --- propuesta → autorización → aplicación ---------------------------------------------------------------
    def proponer(self, proyecto: str, agente: str, archivo: str, contenido: str, motivo: str,
                 origen: str | None = None) -> dict:
        archivo = _rel_segura(archivo)
        if not archivo.endswith(".py"):
            raise ErrorCambio("esta etapa solo admite archivos Python (.py)")
        if len(contenido.encode("utf-8")) > MAX_CONTENIDO:
            raise ErrorCambio("contenido demasiado grande")
        self.proyecto(proyecto)
        antes_h = self._sha_actual(proyecto, archivo)
        antes = (self.lab / self._rel_proyecto(proyecto) / archivo).read_text(encoding="utf-8", errors="replace") \
            if antes_h else ""
        from eq2 import analisis_estatico                 # análisis de V2-F.1: ast.parse, nunca ejecuta
        analisis = analisis_estatico.analizar({archivo: contenido})
        sintaxis = [e for e in analisis.get("errores", []) if e.get("tipo") == "sintaxis"]
        diff = "".join(difflib.unified_diff(antes.splitlines(True), contenido.splitlines(True),
                                            f"a/{archivo}" if antes_h else "/dev/null", f"b/{archivo}"))
        with self.cambios.transaccion():
            n = len(self.cambios.filas("propuestas")) + 1
            pid = f"PROP-{n:04d}"
            self.cambios.insertar("propuestas", {
                "id": pid, "n": n, "proyecto_id": proyecto, "agente": agente, "archivo": archivo,
                "sha256_antes": antes_h, "sha256_despues": _sha(contenido.encode("utf-8")), "contenido": contenido,
                "diff": diff, "analisis": A.canonico(analisis), "autorizable": int(not sintaxis),
                "motivo": motivo, "origen": origen, "ts": A.ahora()})
        return {"estado": "propuesta", "id": pid, "sha256_despues": _sha(contenido.encode("utf-8")),
                "autorizable": not sintaxis, "avisos": analisis.get("avisos", []), "errores": analisis.get("errores", [])}

    def _propuesta(self, pid: str) -> dict:
        if not RE_PROPUESTA.fullmatch(pid or ""):
            raise ErrorCambio(f"identificador de propuesta inválido: {pid!r}")
        filas = self.cambios.filas("propuestas", id=pid)
        if not filas:
            raise ErrorCambio(f"no existe la propuesta {pid}")
        return filas[0]

    def _rechazar(self, pid: str, operacion: str, motivo: str):
        with self.cambios.transaccion():
            k = len(self.cambios.filas("rechazos", propuesta_id=pid)) + 1
            self.cambios.insertar("rechazos", {"id": f"{pid}/R{k}", "propuesta_id": pid, "operacion": operacion,
                                               "motivo": motivo, "ts": A.ahora()})
        raise ErrorCambio(motivo)

    def autorizar(self, pid: str, sha_prefijo: str, minutos: int = 30, acepto_avisos: bool = False) -> dict:
        """SOLO para el usuario (orden de línea de comandos). Ningún agente tiene acceso a esta operación."""
        p = self._propuesta(pid)
        if not p["autorizable"]:
            self._rechazar(pid, "autorizar", "la propuesta tiene errores de sintaxis: no se puede autorizar")
        if not isinstance(sha_prefijo, str) or len(sha_prefijo) < MIN_PREFIJO_SHA \
                or not p["sha256_despues"].startswith(sha_prefijo.lower()):
            self._rechazar(pid, "autorizar", f"confirmación incorrecta: escribe al menos {MIN_PREFIJO_SHA} "
                                             "caracteres del SHA-256 del contenido propuesto")
        avisos = json.loads(p["analisis"]).get("avisos", [])
        if avisos and not acepto_avisos:
            self._rechazar(pid, "autorizar", f"{len(avisos)} avisos de riesgo sin aceptar (--acepto-avisos)")
        if not 1 <= int(minutos) <= 24 * 60:
            self._rechazar(pid, "autorizar", "la caducidad debe estar entre 1 minuto y 24 horas")
        if self.cambios.existe("autorizaciones", propuesta_id=pid):
            self._rechazar(pid, "autorizar", "la propuesta ya tiene una autorización")
        caduca = (self.reloj() + timedelta(minutes=int(minutos))).isoformat()
        with self.cambios.transaccion():
            self.cambios.insertar("autorizaciones", {
                "id": f"AUT-{pid}", "propuesta_id": pid, "actor": "usuario", "sha256_despues": p["sha256_despues"],
                "avisos_aceptados": int(bool(avisos)), "caduca": caduca, "ts": A.ahora()})
        return {"estado": "autorizada", "id": f"AUT-{pid}", "caduca": caduca}

    def aplicar(self, pid: str) -> dict:
        """El controlador escribe el contenido autorizado. Cualquier comprobación fallida se registra y aborta."""
        p = self._propuesta(pid)
        aut = self.cambios.filas("autorizaciones", propuesta_id=pid)
        if not aut:
            self._rechazar(pid, "aplicar", "sin autorización del usuario")
        aut = aut[0]
        if self.cambios.existe("aplicaciones", propuesta_id=pid):
            self._rechazar(pid, "aplicar", "la autorización ya se usó (es de un solo uso)")
        if self.reloj() > datetime.fromisoformat(aut["caduca"]):
            self._rechazar(pid, "aplicar", f"autorización caducada ({aut['caduca']})")
        if aut["sha256_despues"] != p["sha256_despues"] or _sha(p["contenido"].encode("utf-8")) != p["sha256_despues"]:
            self._rechazar(pid, "aplicar", "la autorización no corresponde al contenido propuesto")
        try:
            actual = self._sha_actual(p["proyecto_id"], p["archivo"])
        except ErrorCambio as e:
            self._rechazar(pid, "aplicar", str(e))
        if actual != p["sha256_antes"]:
            self._rechazar(pid, "aplicar", "el archivo cambió desde la propuesta (TOCTOU): no se escribe sobre "
                                           "una versión distinta de la revisada")
        destino = self.lab / self._rel_proyecto(p["proyecto_id"]) / p["archivo"]
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".eq3_", dir=destino.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(p["contenido"])
            os.replace(tmp, destino)                       # atómico: nunca queda un archivo a medias
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        resultado = _sha(destino.read_bytes())
        with self.cambios.transaccion():
            self.cambios.insertar("aplicaciones", {"id": f"APL-{pid}", "propuesta_id": pid,
                                                   "autorizacion_id": aut["id"], "sha256_resultado": resultado,
                                                   "ts": A.ahora()})
        if resultado != p["sha256_despues"]:
            raise ErrorCambio("el archivo escrito no coincide con el contenido autorizado")
        return {"estado": "aplicada", "id": f"APL-{pid}", "archivo": p["archivo"], "sha256": resultado}

    def verificar(self) -> list:
        """Cadena de hashes, coherencia de cada aplicación y estado ACTUAL de los archivos aplicados."""
        problemas = list(self.cambios.verificar_cadena())
        props = {p["id"]: p for p in self.cambios.filas("propuestas")}
        auts = {a["id"]: a for a in self.cambios.filas("autorizaciones")}
        ultima = {}
        for ap in self.cambios.filas("aplicaciones"):
            p, a = props.get(ap["propuesta_id"]), auts.get(ap["autorizacion_id"])
            if p is None or a is None or a["propuesta_id"] != p["id"]:
                problemas.append(f"{ap['id']}: aplicación sin su propuesta o autorización")
                continue
            if ap["sha256_resultado"] != p["sha256_despues"]:
                problemas.append(f"{ap['id']}: el resultado no coincide con lo autorizado")
            clave = (p["proyecto_id"], p["archivo"])
            if clave not in ultima or p["n"] > ultima[clave]["n"]:
                ultima[clave] = p
        for (proyecto, archivo), p in sorted(ultima.items()):
            try:
                actual = self._sha_actual(proyecto, archivo)
            except ErrorCambio as e:
                problemas.append(f"{proyecto}/{archivo}: {e}")
                continue
            if actual != p["sha256_despues"]:
                problemas.append(f"{proyecto}/{archivo}: modificado FUERA del flujo de propuestas (último aplicado: {p['id']})")
        return problemas


def proponer_desde_traza(ctrl: Controlador, traza, eid: str, proyecto: str, archivo: str) -> dict:
    """Lleva la versión recomendada de una ejecución (traza de la Etapa 1) a un proyecto, como propuesta de A1.

    El contenido se lee del laboratorio y se comprueba contra el SHA-256 registrado en la traza: si no coincide,
    no se propone nada.
    """
    res = traza.filas("resultados", ejecucion_id=eid)
    if not res or res[0]["version_recomendada"] is None:
        raise ErrorCambio(f"{eid}: no hay versión recomendada")
    v = res[0]["version_recomendada"]
    cambios = [c for c in traza.filas("cambios", ejecucion_id=eid) if c["version"] == v]
    if len(cambios) != 1:
        raise ErrorCambio(f"{eid}: la versión {v} no tiene exactamente un archivo")
    c = cambios[0]
    contenido = I.leer(ctrl.lab, c["ruta"], MAX_CONTENIDO)
    if _sha(contenido) != c["sha256_despues"]:
        raise ErrorCambio(f"{eid}: el archivo de la versión {v} no coincide con la traza")
    return ctrl.proponer(proyecto, "A1", archivo, contenido.decode("utf-8"),
                         f"versión recomendada v{v} de {eid}", origen=f"traza:{eid}:v{v}")
