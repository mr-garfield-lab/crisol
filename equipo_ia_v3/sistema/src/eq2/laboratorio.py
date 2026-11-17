"""V2-E.2: laboratorio de EXPERIMENTOS (pequeños y medianos). Nunca ejecuta código de los agentes.

Tipos permitidos en esta versión:
  * analisis_estatico : analisis_estatico.analizar sobre TEXTO (ast.parse; no ejecuta)
  * simulacion        : reglas DECLARATIVAS cerradas («si el archivo X contiene T, la prueba P
                        falla»); nada se evalúa ni se importa
  * prueba_motor      : el propio motor con agentes y ejecutor SIMULADOS, en una subcarpeta
Cada experimento registra hipótesis, entradas, límites, resultado, conclusión y evidencia.
Las expectativas usan un vocabulario cerrado (nada de expresiones ni código):
  {"tipo_error": t} {"sin_errores": true} {"prueba_falla": p} {"prueba_pasa": p} {"estado_final": e}
Un error con causa CONFIRMADA puede convertirse en CASO DE REGRESIÓN (datos JSON, no código).

V2-E.4:
  * Experimentos IDEMPOTENTES: con `firma`, reintentar devuelve el mismo experimento; uno que quedó
    'planificado' (proceso interrumpido) se reanuda; su evidencia nunca se duplica.
  * Cada evidencia guarda hipótesis, versión, confianza y limitaciones.
  * Regresiones idempotentes (una por experimento de origen).
  * Interfaz para LABORATORIOS ESPECIALIZADOS (p. ej. el futuro ModLab): ver V2-E.4-r2.

V2-E.4-r2:
  * Los experimentos de REPRODUCCIÓN y CONTROL de una hipótesis solo se crean con
    `planificar_prueba_de_hipotesis()`, que construye la regla A PARTIR DE LA HIPÓTESIS (archivo y
    patrón) y guarda la procedencia (ejecución, versión, SHA-256 del texto). `planificar()` ya no
    acepta `rol` ni `hipotesis_id`: nadie puede fabricar un «control» con una regla o un texto propios.
  * `confirmar_causa_con()` YA NO confirma con una sola reproducción: solo confirma si la hipótesis del
    experimento está RESPALDADA (reproducción + control observados); si no, devuelve False y lo anota.
  * `crear_regresion()` solo parte de la REPRODUCCIÓN de la hipótesis que respalda la causa.
  * Tipos especializados: el registro es SOLO DECLARATIVO. `validar` y `correr` son CÓDIGO NO
    CONFIABLE de terceros: nunca se invocan; planificar o ejecutar un tipo especializado se rechaza.
    Las propiedades declaradas (`ejecuta_codigo`, `usa_red`) NO son una garantía ni un aislamiento.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass

from . import analisis_estatico, config, ejecutor, motor, rutas, sanea
from . import incidencias as inc_mod

TIPOS = ("analisis_estatico", "simulacion", "prueba_motor")
EVIDENCIA_DE_TIPO = {"analisis_estatico": "analisis_estatico", "simulacion": "simulacion",
                     "prueba_motor": "simulacion"}


class TipoNoEjecutable(PermissionError):
    """Un tipo especializado está registrado solo como declaración: su código no se ejecuta."""


@dataclass(frozen=True)
class TipoExperimento:
    """DECLARACIÓN de un tipo de experimento especializado (interfaz futura, p. ej. ModLab).

    `validar` y `correr` son CÓDIGO NO CONFIABLE de terceros. En esta versión NUNCA se invocan: ni al
    registrar, ni al planificar, ni al ejecutar. Los campos `ejecuta_codigo` y `usa_red` son lo que el
    tipo DECLARA de sí mismo; el registro rechaza los que declaran algo prohibido, pero una declaración
    no es una garantía: este registro NO es un aislamiento de seguridad. Ejecutarlos exigirá en el
    futuro un aislamiento real y una autorización explícita del usuario."""
    nombre: str
    tipo_evidencia: str                 # 'analisis_estatico' | 'simulacion' (nunca 'prueba_real')
    validar: object
    correr: object
    descripcion: str = ""
    especialidad: str = "general"
    ejecuta_codigo: bool = False
    usa_red: bool = False


TIPOS_ESPECIALIZADOS = {}
_NOMBRE_TIPO = re.compile(r"[a-z_]{3,40}")


def registrar_tipo(t: TipoExperimento) -> None:
    """Registra la DECLARACIÓN (no habilita su ejecución). No invoca ninguna función del tipo."""
    if not isinstance(t, TipoExperimento):
        raise TypeError("se esperaba un TipoExperimento")
    if t.ejecuta_codigo or t.usa_red:
        raise PermissionError("un laboratorio especializado no puede ejecutar código ni usar la red")
    if t.tipo_evidencia not in ("analisis_estatico", "simulacion"):
        raise PermissionError("un tipo especializado solo produce evidencia estática o simulada")
    if not _NOMBRE_TIPO.fullmatch(t.nombre or "") or t.nombre in TIPOS or t.nombre in TIPOS_ESPECIALIZADOS:
        raise ValueError(f"nombre de tipo inválido o repetido: {t.nombre!r}")
    if not (callable(t.validar) and callable(t.correr)):
        raise TypeError("validar y correr deben ser invocables")
    TIPOS_ESPECIALIZADOS[t.nombre] = t


def retirar_tipo(nombre: str) -> None:
    TIPOS_ESPECIALIZADOS.pop(nombre, None)
EXPECTATIVAS = ("tipo_error", "sin_errores", "prueba_falla", "prueba_pasa", "estado_final")
DE_FALLO = ("tipo_error", "prueba_falla")
MAX_ENTRADAS_BYTES = 60_000
LIMITACIONES = {
    "analisis_estatico": "análisis estático del texto: detecta errores de forma, no de comportamiento",
    "simulacion": "simulación con reglas declarativas o guion: NO es ejecución ni prueba real",
}
MAX_REGLAS = 20


def ajustar_presupuesto(base: "motor.Presupuesto", recursos: dict):
    """Reduce (nunca amplía) el presupuesto según los recursos medidos. Devuelve (presupuesto, motivos)."""
    b = base.acotado()
    it, ll, seg, arch = b.max_iteraciones_correccion, b.max_llamadas, b.seg_total, b.max_archivos
    motivos = []
    mem = recursos.get("mem_kB")
    if mem is None:
        it, ll = min(it, 1), min(ll, 6)
        motivos.append("memoria no medible: presupuesto mínimo")
    elif mem < 1_000_000:
        it, ll, arch = min(it, 1), min(ll, 6), min(arch, 4)
        motivos.append(f"memoria baja ({mem} kB)")
    elif mem < 2_000_000:
        it = min(it, 2)
        motivos.append(f"memoria moderada ({mem} kB)")
    pct, cargando = recursos.get("bateria") or (None, None)
    if pct is not None and pct < 30 and not cargando:
        seg = min(seg, b.seg_total / 2)
        motivos.append(f"batería {pct} % sin cargar")
    return motor.Presupuesto(it, ll, seg, b.seg_por_prueba, arch, b.max_bytes_archivo,
                             b.max_bytes_total).acotado(), motivos


def _simular(entradas) -> dict:
    """Reglas cerradas: no se evalúa nada del texto, solo se buscan subcadenas."""
    archivos = entradas.get("archivos") or {}
    pruebas = {p: "ok" for p in entradas.get("pruebas") or []}
    for r in (entradas.get("reglas") or [])[:MAX_REGLAS]:
        if r.get("resultado") not in ("ok", "fallo"):
            raise ValueError("regla de simulación inválida")
        cont = archivos.get(r.get("archivo"), "")
        if isinstance(r.get("si_contiene"), str) and r["si_contiene"] in cont:
            pruebas[r["prueba"]] = r["resultado"]
    fallidas = sorted(p for p, v in pruebas.items() if v == "fallo")
    return {"pruebas": pruebas, "fallidas": fallidas, "tipo": "simulado"}


ESCENARIOS = ("demo_corrige", "bloqueo_persistente", "sin_progreso")


def _escenario(nombre):
    def plan(paso, n, **kw):
        if paso == "planificar":
            return "ARCHIVOS: m.py, test_m.py\nCRITERIO: C1 | no muta | PRUEBA: test_no_muta"
        if paso == "evaluar":
            return "DIAGNOSTICO: usar sorted"
        if paso == "revisar":
            if nombre == "bloqueo_persistente":
                return "BLOQUEO: riesgo crítico"
            return "OBJECION: muta | EVIDENCIA: .sort()" if ".sort()" in kw["archivos"] else "SIN OBJECIONES: ok"
        arreglado = paso == "corregir" and nombre == "demo_corrige"
        cuerpo = "    return sorted(xs)" if arreglado else "    xs.sort()\n    return xs"
        return (f"ARCHIVO: m.py\n```python\ndef ordenar(xs):\n{cuerpo}\n```\nARCHIVO: test_m.py\n```python\n"
                "from m import ordenar\ndef test_no_muta():\n    a = [2, 1]\n    ordenar(a)\n    assert a == [2, 1]\n```")

    def ejec(it, arch):
        muta = ".sort()" in arch.get("m.py", "")
        return {"estado": "fallos" if muta else "ok", "pruebas_total": 1, "pruebas_fallidas": int(muta),
                "detalle": {"pruebas": {"test_no_muta": "fallo" if muta else "ok"}}}
    return plan, ejec


def _concluir(esperado: dict, tipo: str, r: dict) -> str:
    (clave, valor), = esperado.items()
    if clave == "tipo_error":
        return "apoya" if any(e["tipo"] == valor for e in r.get("errores", [])) else "refuta"
    if clave == "sin_errores":
        return "apoya" if not r.get("errores") else "refuta"
    if clave in ("prueba_falla", "prueba_pasa"):
        estado = (r.get("pruebas") or {}).get(valor)
        if estado is None:
            return "no_concluyente"
        return "apoya" if estado == ("fallo" if clave == "prueba_falla" else "ok") else "refuta"
    if clave == "estado_final":
        return "apoya" if r.get("estado_final") == valor else "refuta"
    return "no_concluyente"


class Laboratorio:
    def __init__(self, registro: inc_mod.RegistroIncidencias, presupuesto: "motor.Presupuesto" = None,
                 reloj=time.monotonic, recursos: dict = None):
        self.reg, self.lab, self.reloj = registro, registro.lab, reloj
        base = presupuesto or motor.Presupuesto()
        self.presupuesto, self.ajustes = ajustar_presupuesto(base, recursos or {"mem_kB": 4_000_000})
        self.lab.crear_dir("incidencias", "laboratorio")

    @staticmethod
    def _validar(tipo, entradas, esperado):
        if tipo in TIPOS_ESPECIALIZADOS:
            raise TipoNoEjecutable(f"'{tipo}' es un tipo especializado registrado solo como declaración: su "
                                   "código es no confiable y no se ejecuta en esta versión")
        if tipo not in TIPOS:
            raise ValueError("tipo de experimento no permitido en esta versión")
        if not isinstance(entradas, dict):
            raise ValueError("entradas: diccionario")
        if not isinstance(esperado, dict) or len(esperado) != 1 or next(iter(esperado)) not in EXPECTATIVAS:
            raise ValueError("expectativa fuera del vocabulario cerrado")
        if len(json.dumps(entradas, default=str)) > MAX_ENTRADAS_BYTES:
            raise ValueError("entradas demasiado grandes")
        if tipo == "prueba_motor" and entradas.get("escenario") not in ESCENARIOS:
            raise ValueError("escenario desconocido")
        if tipo in ("analisis_estatico", "simulacion"):
            arch = entradas.get("archivos")
            if not isinstance(arch, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in arch.items()):
                raise ValueError("archivos: diccionario de texto")

    def planificar(self, hipotesis, tipo, entradas, esperado, incidencia_id=None, firma=None, version=None,
                   confianza=None, limitaciones=None) -> str:
        """Experimento LIBRE (sin rol). Con `firma`, IDEMPOTENTE. Un experimento libre nunca cuenta como
        reproducción ni como control de una hipótesis (ver planificar_prueba_de_hipotesis)."""
        self._validar(tipo, entradas, esperado)
        return self._insertar(hipotesis, tipo, entradas, esperado, incidencia_id, firma, None, None, version,
                              None, None, confianza, limitaciones)

    def _insertar(self, hipotesis, tipo, entradas, esperado, incidencia_id, firma, rol, hipotesis_id, version,
                  run_id, archivo_sha256, confianza, limitaciones) -> str:
        if incidencia_id:
            self.reg.obtener(incidencia_id)
        if firma is not None:
            r = self.reg.con.execute("SELECT id FROM experimentos WHERE firma=?", (firma,)).fetchone()
            if r:
                return r[0]
        limites = {"presupuesto": self.presupuesto.__dict__, "ajustes": self.ajustes,
                   "ejecucion_real": False, "confianza": confianza,
                   "limitaciones": sanea.limpiar(limitaciones, 300) if limitaciones else None}
        with self.reg.con:
            c = self.reg.con.execute(
                "INSERT INTO experimentos(id,creado,hipotesis,tipo,entradas_json,limites_json,estado,incidencia_id,"
                "firma,rol,hipotesis_id,version,run_id,archivo_sha256) "
                "VALUES('pendiente',?,?,?,?,?,'planificado',?,?,?,?,?,?,?)",
                (self.reg.ahora(), sanea.limpiar(hipotesis, 500), tipo,
                 json.dumps({"entradas": entradas, "esperado": esperado}, ensure_ascii=False),
                 json.dumps(limites, default=str), incidencia_id, firma, rol, hipotesis_id, version,
                 run_id, archivo_sha256))
            eid = inc_mod._ident("EXP", c.lastrowid)
            self.reg.con.execute("UPDATE experimentos SET id=? WHERE num=?", (eid, c.lastrowid))
        return eid

    def planificar_prueba_de_hipotesis(self, hid, rol, run_id, version, texto, limitaciones=None) -> str:
        """REPRODUCCIÓN (el patrón está en la versión donde se observó el fallo) o CONTROL (el patrón no
        está en una versión donde el fallo ya no se observa). La regla y la expectativa se construyen
        AQUÍ a partir de la hipótesis; la procedencia (ejecución, versión, SHA-256 del texto) se guarda
        para que la base la compare con las observaciones del motor. Idempotente."""
        if rol not in ("reproduccion", "control"):
            raise ValueError("rol inválido")
        hs = self.reg.hipotesis(hid=hid)
        if not hs:
            raise KeyError(hid)
        h = hs[0]
        texto = texto if isinstance(texto, str) else ""
        sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        prueba = f"fallo_{h['incidencia_id'].replace('-', '_').lower()}"
        entradas = {"archivos": {h["archivo"]: texto}, "pruebas": [prueba],
                    "reglas": [{"archivo": h["archivo"], "si_contiene": h["patron"], "prueba": prueba,
                                "resultado": "fallo"}]}
        esperado = {"prueba_falla": prueba} if rol == "reproduccion" else {"prueba_pasa": prueba}
        self._validar("simulacion", entradas, esperado)
        firma = hashlib.sha256(f"{hid}|{rol}|{sha}".encode("utf-8")).hexdigest()[:32]
        return self._insertar(f"{hid} [{rol}] patrón '{h['patron']}' en {h['archivo']} (v{version})", "simulacion",
                              entradas, esperado, h["incidencia_id"], firma, rol, hid, int(version), run_id, sha,
                              0.3 if rol == "reproduccion" else 0.6, limitaciones)

    def experimento(self, eid) -> dict:
        r = self.reg.con.execute("SELECT * FROM experimentos WHERE id=?", (eid,)).fetchone()
        if r is None:
            raise KeyError(eid)
        d = dict(r)
        d.update(json.loads(d.pop("entradas_json")))
        d["limites"] = json.loads(d.pop("limites_json"))
        d["resultado"] = json.loads(d.pop("resultado_json")) if d["resultado_json"] else None
        return d

    def _correr(self, tipo, entradas, eid):
        if tipo == "analisis_estatico":
            return dict(analisis_estatico.analizar(entradas["archivos"]), tipo="estatico")
        if tipo == "simulacion":
            return _simular(entradas)
        if tipo in TIPOS_ESPECIALIZADOS or tipo not in TIPOS:          # defensa: nunca se invoca código ajeno
            raise TipoNoEjecutable(f"tipo '{tipo}' no ejecutable en esta versión")
        plan, ejec = _escenario(entradas["escenario"])
        m = motor.Motor(self.lab.base / "incidencias" / "laboratorio" / eid.lower(),
                        motor.AgentesMotorSimulados(plan), ejecutor.EjecutorSimulado(ejec),
                        presupuesto=self.presupuesto, raiz_laboratorio=self.lab.raiz)
        inf = m.ejecutar("Experimento del motor: " + entradas["escenario"])
        return {"estado_final": inf["estado_final"], "iteraciones": inf["iteraciones_correccion"],
                "llamadas": inf["llamadas_agentes"], "resultado": inf["resultado"], "tipo": "simulado"}

    def ejecutar(self, eid) -> dict:
        """Ejecuta un experimento 'planificado'. Orden seguro ante interrupciones: primero la evidencia
        (sin duplicar si ya existe una de este experimento), después se cierra el experimento. Si el
        proceso muere entre ambos pasos, el experimento sigue 'planificado' y se puede reanudar."""
        e = self.experimento(eid)
        if e["estado"] != "planificado":
            raise ValueError("el experimento ya se ejecutó")
        t0 = self.reloj()
        try:
            r = self._correr(e["tipo"], e["entradas"], eid)
            estado = "completado"
            concl = _concluir(e["esperado"], e["tipo"], r)
        except (ValueError, OSError, rutas.RutaInsegura) as ex:
            r, estado, concl = {"error": f"{type(ex).__name__}: {ex}"[:300]}, "abortado", "no_concluyente"
        r["duracion_s"] = round(self.reloj() - t0, 3)
        clave = next(iter(e["esperado"]))
        resultado_ev = ("informativa" if concl != "apoya" else
                        "fallida" if clave in DE_FALLO else "superada")
        if e["tipo"] not in EVIDENCIA_DE_TIPO:
            raise TipoNoEjecutable(f"tipo '{e['tipo']}' no ejecutable en esta versión")
        tipo_ev = EVIDENCIA_DE_TIPO[e["tipo"]]
        previa = self.reg.con.execute("SELECT num FROM evidencias WHERE experimento_id=? AND tipo IN "
                                      "('analisis_estatico','simulacion') ORDER BY num LIMIT 1", (eid,)).fetchone()
        lim = e["limites"]
        if previa:
            ev = previa[0]
        else:
            ev = self.reg.registrar_evidencia(
                e["incidencia_id"], tipo_ev, resultado_ev,
                f"{eid}{' [' + e['rol'] + ']' if e.get('rol') else ''}: {e['hipotesis'][:200]} -> {concl}",
                "laboratorio", contenido={"experimento": eid, "resultado": r, "conclusion": concl},
                experimento_id=eid, hipotesis_id=e.get("hipotesis_id"), version=e.get("version"),
                confianza=lim.get("confianza") if concl == "apoya" else 0.0,
                limitaciones=lim.get("limitaciones") or LIMITACIONES[tipo_ev])
        self._cerrar(eid, estado, r, concl, ev)
        return {"id": eid, "estado": estado, "conclusion": concl, "resultado": r, "evidencia": resultado_ev,
                "evidencia_num": ev, "ejecucion_real": False}

    def _cerrar(self, eid, estado, r, concl, ev):
        with self.reg.con:
            self.reg.con.execute("UPDATE experimentos SET estado=?, resultado_json=?, conclusion=?, evidencia_num=? "
                                 "WHERE id=?", (estado, json.dumps(r, ensure_ascii=False, default=str), concl, ev, eid))

    def confirmar_causa_con(self, eid) -> bool:
        """V2-E.4-r2: confirma la causa SOLO si el experimento es de una hipótesis ya RESPALDADA de esa
        incidencia (reproducción + control sobre versiones observadas). Un experimento aislado, aunque
        reproduzca el fallo, NO basta: devuelve False y deja constancia del motivo."""
        e = self.experimento(eid)
        iid = e["incidencia_id"]
        if not iid:
            return False
        h = self.reg.hipotesis(hid=e["hipotesis_id"]) if e.get("hipotesis_id") else []
        if not h or h[0]["estado"] != "respaldada" or h[0]["incidencia_id"] != iid:
            motivo = (f"{eid}: confirmación rechazada; hace falta una hipótesis respaldada (reproducción y control "
                      "sobre versiones observadas); un experimento aislado no basta")
            ya = self.reg.con.execute("SELECT 1 FROM evidencias WHERE incidencia_id=? AND tipo='registro' AND "
                                      "descripcion=?", (iid, motivo)).fetchone()
            if not ya:
                self.reg.registrar_evidencia(iid, "registro", "informativa", motivo, "laboratorio",
                                             limitaciones="la causa sigue siendo una hipótesis")
            return False
        inc = self.reg.obtener(iid)
        if not (inc["causa_estado"] == "confirmada" and inc["causa_hipotesis"] == h[0]["id"]):
            self.reg.confirmar_causa(iid, "laboratorio", f"{h[0]['id']} respaldada", respaldo="simulacion",
                                     hipotesis_id=h[0]["id"])
        return True

    # --- casos de regresión --------------------------------------------------------------------
    def crear_regresion(self, eid) -> str:
        """Idempotente: si ya existe la regresión de este experimento, devuelve su id."""
        previa = self.reg.con.execute("SELECT id, archivo FROM regresiones WHERE origen=?", (eid,)).fetchone()
        if previa:
            self._asegurar_archivo(previa[0])
            return previa[0]
        e = self.experimento(eid)
        if e["tipo"] not in ("analisis_estatico", "simulacion"):
            raise ValueError("solo experimentos estáticos o simulados se convierten en regresión")
        if not e["incidencia_id"]:
            raise ValueError("el experimento no está ligado a una incidencia")
        inc = self.reg.obtener(e["incidencia_id"])
        if inc["causa_estado"] != "confirmada":
            raise inc_mod.PermisoDenegado("solo un error CONFIRMADO se convierte en regresión")
        if e["conclusion"] != "apoya" or next(iter(e["esperado"])) not in DE_FALLO:
            raise ValueError("el experimento no reproduce el fallo")
        if e.get("rol") != "reproduccion" or not e.get("hipotesis_id") or e["hipotesis_id"] != inc["causa_hipotesis"]:
            # V2-E.4-r2: solo la reproducción de la hipótesis que respalda la causa.
            raise inc_mod.PermisoDenegado("la regresión parte de la reproducción de la hipótesis que respalda la causa")
        caso = {"tipo": e["tipo"], "entradas": e["entradas"], "condicion_fallo": e["esperado"],
                "incidencia": e["incidencia_id"], "origen": eid, "nota": "datos, no código"}
        texto = json.dumps(caso, ensure_ascii=False, indent=2)
        sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        with self.reg.con:
            c = self.reg.con.execute(
                "INSERT INTO regresiones(id,creado,incidencia_id,tipo,entradas_json,esperado_json,sha256,origen,"
                "hipotesis_id) VALUES('pendiente',?,?,?,?,?,?,?,?)",
                (self.reg.ahora(), e["incidencia_id"], e["tipo"], json.dumps(e["entradas"], ensure_ascii=False),
                 json.dumps(e["esperado"]), sha, eid, e.get("hipotesis_id")))
            rid = inc_mod._ident("REG", c.lastrowid)
            self.reg.con.execute("UPDATE regresiones SET id=?, archivo=? WHERE num=?",
                                 (rid, f"regresiones/{rid}.json", c.lastrowid))
        self.lab.escribir_atomico(("incidencias", "regresiones", f"{rid}.json"), texto)
        return rid

    def _caso(self, r) -> dict:
        return {"tipo": r["tipo"], "entradas": json.loads(r["entradas_json"]),
                "condicion_fallo": json.loads(r["esperado_json"]), "incidencia": r["incidencia_id"],
                "origen": r["origen"], "nota": "datos, no código"}

    def _asegurar_archivo(self, rid):
        """Si el proceso murió entre la base y el archivo, lo escribe ahora (nunca sobrescribe)."""
        r = self.reg.con.execute("SELECT * FROM regresiones WHERE id=?", (rid,)).fetchone()
        p = self.lab.base / "incidencias" / "regresiones" / f"{rid}.json"
        if r is not None and not p.exists():
            self.lab.escribir_atomico(("incidencias", "regresiones", f"{rid}.json"),
                                      json.dumps(self._caso(r), ensure_ascii=False, indent=2))

    def regresiones(self) -> list:
        return [dict(r) for r in self.reg.con.execute("SELECT * FROM regresiones ORDER BY num").fetchall()]

    def ejecutar_regresion(self, rid, archivos=None) -> dict:
        """Sin `archivos`: comprueba que el caso aún REPRODUCE el fallo (detector sano).
        Con `archivos` (versión nueva): la regresión SE SUPERA si la condición de fallo ya no se da."""
        r = self.reg.con.execute("SELECT * FROM regresiones WHERE id=?", (rid,)).fetchone()
        if r is None:
            raise KeyError(rid)
        entradas = json.loads(r["entradas_json"])
        cond = json.loads(r["esperado_json"])
        if archivos is not None:
            entradas = dict(entradas, archivos=archivos)
        res = (dict(analisis_estatico.analizar(entradas["archivos"]), tipo="estatico")
               if r["tipo"] == "analisis_estatico" else _simular(entradas))
        hay_fallo = _concluir(cond, r["tipo"], res) == "apoya"
        return {"id": rid, "modo": "original" if archivos is None else "version_nueva",
                "fallo_presente": hay_fallo,
                "supera": (not hay_fallo) if archivos is not None else None,
                "reproduce": hay_fallo if archivos is None else None, "tipo": res["tipo"],
                "ejecucion_real": False}
