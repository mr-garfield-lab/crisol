"""V2-D: ciclo autónomo plan -> generar -> revisar -> ejecutar -> corregir (ARQUITECTURA).

  1. A2 analiza la tarea y propone un plan.
  2. A1 genera los archivos (formato 'ARCHIVO: nombre' + bloque ```).
  3. A3 revisa la solución (OBJECION | EVIDENCIA / SIN OBJECIONES / FALTA).
  4. Un EJECUTOR restringido realiza las pruebas  -> en V2-D solo simulado o no disponible.
  5. Los resultados vuelven a los agentes como DATOS NO CONFIABLES.
  6. A1 corrige; 7. se repite hasta cumplir los criterios o agotar los límites.
  8. Informe final (runs/<run>/ciclo/informe.json) + registro de acciones (acciones.jsonl).

Nada de lo que escriben los agentes se ejecuta aquí. Con un ejecutor simulado el informe dice
verificacion='simulada'; con el ejecutor no disponible, 'ninguna' y estado 'sin_verificar'.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime

from . import archivos, config, contexto, memoria, prompts, rutas, sanea, votos
from .ejecutor import EjecutorBase, EspacioTrabajo, Politica, RegistroAcciones, Resultado
from .inferencia import BackendBase, ErrorInferencia

ESTADOS_FINALES = ("criterios_cumplidos", "sin_verificar", "limite_iteraciones", "limite_llamadas",
                   "limite_tiempo", "detenido", "error_inferencia", "politica_rechazada",
                   "ejecutor_rechazo")


class Agentes:
    """Interfaz: tres métodos que devuelven TEXTO no confiable."""
    llamadas = 0

    def plan(self, tarea: str) -> str:
        raise NotImplementedError

    def generar(self, tarea: str, plan: str, retro: str) -> str:
        raise NotImplementedError

    def revisar(self, tarea: str, archivos_txt: str) -> str:
        raise NotImplementedError


class AgentesSimulados(Agentes):
    """guion(paso, n, **kw) -> str. Para pruebas y para el modo ciclo_simulado."""

    def __init__(self, guion):
        self.guion, self.llamadas = guion, 0

    def _g(self, paso, **kw):
        self.llamadas += 1
        return self.guion(paso, self.llamadas, **kw)

    def plan(self, tarea):
        return self._g("plan", tarea=tarea)

    def generar(self, tarea, plan, retro):
        return self._g("generar", tarea=tarea, plan=plan, retro=retro)

    def revisar(self, tarea, archivos_txt):
        return self._g("revisar", tarea=tarea, archivos=archivos_txt)


INSTR_CICLO = {
    "plan": ("Analiza la tarea y escribe un plan breve: archivos a crear, funciones y casos de "
             "prueba (máx. 6 líneas). Si falta un dato necesario, escribe 'FALTA: <dato>'."),
    "generar": ("Escribe los archivos de la solución. Para cada archivo: una línea "
                "'ARCHIVO: nombre.py' y debajo su contenido completo en un bloque ```. Incluye un "
                "archivo test_<nombre>.py con pruebas. Si hay resultados de pruebas anteriores, "
                "corrige los errores que indican. No incluyas instrucciones para ejecutar nada."),
    "revisar": prompts.INSTRUCCION["revision"],
}
MAX_GEN_CICLO = {"plan": 160, "generar": 400, "revisar": 160}
AGENTE_PASO = {"plan": "A2", "generar": "A1", "revisar": "A3"}


class AgentesLLM(Agentes):
    """Agentes sobre un backend (simulado o real). Usa el empaquetado de contexto con
    presupuesto y delimitadores de datos no confiables. No toca SQLite."""

    def __init__(self, backend: BackendBase, plazo_s=None):
        if not isinstance(backend, BackendBase):
            raise TypeError("backend inválido")
        self.backend, self.llamadas = backend, 0
        self.plazo_s = plazo_s or config.SEG_POR_LLAMADA
        self.ultima_terminacion = {}

    def _pedir(self, paso, tarea, bloques):
        fijo = INSTR_CICLO[paso] + "\n\n" + sanea.envolver("tarea", tarea, config.MAX_TAREA_CHARS)
        bl = [contexto.Bloque(n, t, i, cap) for i, (n, t, cap) in enumerate(bloques) if t]
        p = contexto.construir(prompts.SISTEMA[AGENTE_PASO[paso]], fijo, bl, MAX_GEN_CICLO[paso])
        self.llamadas += 1
        r = self.backend.completar(p.mensajes(), p.max_gen, self.plazo_s)
        self.ultima_terminacion[paso] = votos.terminacion(getattr(r, "finish_reason", None))
        return r.texto if isinstance(getattr(r, "texto", None), str) else ""

    def plan(self, tarea):
        return self._pedir("plan", tarea, [])

    def generar(self, tarea, plan, retro):
        return self._pedir("generar", tarea, [("plan", plan, 600), ("resultados_pruebas", retro, 700)])

    def revisar(self, tarea, archivos_txt):
        return self._pedir("revisar", tarea, [("archivos", archivos_txt, 1500)])


class Ciclo:
    def __init__(self, base, agentes: Agentes, ejecutor: EjecutorBase, politica: Politica = None,
                 max_iteraciones=config.EJECUTOR_MAX_ITERACIONES, max_llamadas=None,
                 seg_total=config.SEG_POR_TAREA, reloj=time.monotonic, ahora=memoria.ahora_iso,
                 raiz_laboratorio=None):
        raiz = raiz_laboratorio if raiz_laboratorio is not None else rutas.raiz_laboratorio()
        self.lab = rutas.Laboratorio(raiz, base)
        self.base = self.lab.base
        self.agentes, self.ejecutor = agentes, ejecutor
        self.politica = politica or Politica()
        # Límites DUROS: nunca por encima de los de config, aunque se pidan más.
        self.max_iteraciones = max(1, min(int(max_iteraciones), config.EJECUTOR_MAX_ITERACIONES))
        tope = 1 + 2 * self.max_iteraciones
        self.max_llamadas = tope if max_llamadas is None else max(1, min(int(max_llamadas), tope))
        self.seg_total = min(float(seg_total), float(config.SEG_POR_TAREA))
        self.reloj, self.ahora = reloj, ahora
        self._parar = False

    def solicitar_parada(self):
        self._parar = True

    def _motivo_parada(self):
        if self._parar:
            return "senal"
        if os.path.lexists(str(self.base / "STOP")):
            return "stop_usuario"
        return None

    def _limite(self, t0, antes_de_llamar=True):
        """El tope de llamadas solo se comprueba ANTES de una llamada a los agentes."""
        m = self._motivo_parada()
        if m:
            return "detenido", m
        if self.reloj() - t0 > self.seg_total:
            return "limite_tiempo", None
        if antes_de_llamar and self.agentes.llamadas >= self.max_llamadas:
            return "limite_llamadas", None
        return None, None

    def ejecutar(self, tarea: str) -> dict:
        tarea_l = sanea.limpiar(tarea, config.MAX_TAREA_CHARS + 1)
        if not tarea_l or len(tarea_l) > config.MAX_TAREA_CHARS:
            raise ValueError("tarea vacía o demasiado larga")
        self.lab.crear_base()
        self.lab.crear_dir("runs")
        self.lab.crear_dir_exclusivo("lock")                 # FileExistsError si hay otra sesión
        try:
            self.lab.crear_exclusivo(("lock", "pid"), str(os.getpid()))
            run_id = "ciclo_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"
            self.lab.crear_dir("runs", run_id, "ciclo")
            reg = RegistroAcciones(self.lab, ("runs", run_id, "ciclo", "acciones.jsonl"), self.ahora)
            informe = self._bucle(tarea_l, run_id, reg)
            self.lab.crear_exclusivo(("runs", run_id, "ciclo", "informe.json"),
                                     json.dumps(informe, ensure_ascii=False, indent=2, default=str))
            return informe
        finally:
            self.lab.quitar_candado()

    def _bucle(self, tarea, run_id, reg) -> dict:
        t0 = self.reloj()
        inf = {"run_id": run_id, "tarea": tarea, "ejecutor": self.ejecutor.nombre,
               "verificacion": ("simulada" if self.ejecutor.simulado else
                                "ninguna" if self.ejecutor.aislamiento == "ninguno" else "real"),
               "iteraciones": [], "estado": None, "motivo": None, "archivos_finales": [],
               "limites": {"max_iteraciones": self.max_iteraciones, "max_llamadas": self.max_llamadas,
                           "seg_total": self.seg_total},
               "nota": "Los archivos son TEXTO del modelo: no se han ejecutado."}
        pr = self.politica.problemas()
        if pr:
            reg.anotar("politica_rechazada", problemas=pr)
            inf.update(estado="politica_rechazada", motivo="; ".join(pr))
            return inf
        reg.anotar("inicio", tarea_sha=hashlib.sha256(tarea.encode("utf-8")).hexdigest(),
                   ejecutor=self.ejecutor.nombre, politica=self.politica.__dict__)
        try:
            plan = self.agentes.plan(tarea)
            reg.anotar("plan", agente="A2", chars=len(plan or ""))
            retro = ""
            for it in range(1, self.max_iteraciones + 1):
                est, mot = self._limite(t0)
                if est:
                    inf.update(estado=est, motivo=mot)
                    break
                fila = {"n": it}
                inf["iteraciones"].append(fila)
                txt = self.agentes.generar(tarea, plan, retro)
                ex = archivos.extraer(txt)
                fila["archivos"] = [{k: a[k] for k in ("nombre", "bytes", "sha256")} for a in ex["archivos"]]
                fila["problemas_archivos"] = ex["problemas"]
                reg.anotar("generar", agente="A1", iteracion=it, archivos=fila["archivos"],
                           problemas=ex["problemas"])
                if not ex["archivos"]:
                    retro = "No se pudieron extraer archivos: " + ", ".join(ex["problemas"])
                    fila["resultado"] = "sin_archivos"
                    continue
                esp = EspacioTrabajo(self.lab, run_id, it)
                for a in ex["archivos"]:
                    esp.escribir(a["nombre"], a["contenido"], self.politica)
                    reg.anotar("escribir_archivo", iteracion=it, nombre=a["nombre"], bytes=a["bytes"])
                est, mot = self._limite(t0)
                if est:
                    inf.update(estado=est, motivo=mot)
                    break
                juntos = "\n".join(f"ARCHIVO: {a['nombre']}\n{a['contenido']}" for a in ex["archivos"])
                rev = self.agentes.revisar(tarea, juntos)
                ar = votos.analizar_revision(rev or "")
                fila["revision"] = ar
                reg.anotar("revisar", agente="A3", iteracion=it, **ar)
                est, mot = self._limite(t0, antes_de_llamar=False)
                if est:
                    inf.update(estado=est, motivo=mot)
                    break
                res = self.ejecutor.ejecutar(esp, "pruebas_python", self.politica)
                fila["ejecucion"] = res.a_dict()
                reg.anotar("ejecutar", iteracion=it, ejecutor=self.ejecutor.nombre, estado=res.estado,
                           pruebas_total=res.pruebas_total, pruebas_fallidas=res.pruebas_fallidas,
                           simulado=res.simulado)
                inf["archivos_finales"] = fila["archivos"]
                if res.estado == "no_disponible":
                    inf.update(estado="sin_verificar", motivo="ejecutor_no_disponible")
                    break
                if res.estado == "rechazado":
                    inf.update(estado="ejecutor_rechazo", motivo=res.salida)
                    break
                if res.estado == "detenido":
                    inf.update(estado="detenido", motivo="ejecutor")
                    break
                ok = (res.estado == "ok" and res.pruebas_total > 0 and res.pruebas_fallidas == 0
                      and ar["objeciones"] == 0)
                fila["criterios"] = ok
                if ok:
                    inf.update(estado="criterios_cumplidos", motivo=None)
                    break
                objeciones = [l for l in (rev or "").split("\n") if "OBJECI" in l.upper()][:5]
                retro = ("Resultado de las pruebas: " + res.estado
                         + f" ({res.pruebas_fallidas}/{res.pruebas_total} fallidas)\n"
                         + sanea.limpiar(res.salida, 500) + "\n" + "\n".join(objeciones))
            else:
                inf.update(estado="limite_iteraciones", motivo=None)
        except ErrorInferencia as e:
            inf.update(estado="error_inferencia", motivo=e.motivo)
            reg.anotar("error_inferencia", motivo=e.motivo)
        if inf["estado"] is None:
            inf["estado"] = "limite_iteraciones"
        inf["llamadas_agentes"] = self.agentes.llamadas
        inf["duracion_s"] = round(self.reloj() - t0, 3)
        reg.anotar("fin", estado=inf["estado"], motivo=inf["motivo"])
        return inf
