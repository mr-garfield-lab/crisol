"""Equipo IA V3 · GRAFO Y CONTEXTO (Etapa 2), reutilizando Contexto Ligero V3.5 sin modificarlo.

`contexto_ligero/` es una copia IDÉNTICA (byte a byte, comprobada por una prueba) de
`fuentes/contexto_ligero_v35/{contexto_core, contexto_v3.py}` y de sus tareas de benchmark.

- **Código:** `Grafo.indexar()` construye un índice SQLite con archivos, símbolos y aristas de llamada entre
  símbolos. Es INCREMENTAL: solo reprocesa los archivos cuyo SHA-256 cambió y elimina los desaparecidos
  (invalidación).
- **Recuperación:** `recuperar()` devuelve archivos y símbolos con su SHA-256 actual. `paquete()` arma un contexto
  dentro de un presupuesto de tokens ESTIMADOS (no son los de Qwen). `dependencias()` calcula la clausura de
  llamadas indexadas, que nunca se declara completa en tiempo de ejecución.
- **Tareas y decisiones:** `importar_traza()` lleva al grafo de Contexto Ligero los objetivos, ejecuciones,
  decisiones, versiones y experiencias de la traza unificada (Etapa 1), con aristas `depends_on` (acíclicas)
  y `relates_to`.
- **Medición:** `medir()` calcula el recall@k frente a los oráculos PRERREGISTRADOS por Contexto Ligero
  (`benchmarks/tasks_*.json`, «declared_before_benchmark»). Lo compara con una línea ingenua: archivos ordenados
  por la frecuencia de los términos de la consulta.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import RAIZ
from . import traza as T

CONTEXTO = RAIZ / "contexto_ligero"
if str(CONTEXTO) not in sys.path:
    sys.path.append(str(CONTEXTO))
from contexto_core import dependencies, index, packets, retrieval  # noqa: E402

from .plataforma import adaptar_contexto_ligero  # noqa: E402

# Windows no tiene dir_fd/O_NOFOLLOW y Contexto Ligero falla cerrado (no indexaría nada): lectura equivalente de
# eq3.plataforma, sin tocar los archivos de Contexto Ligero. En Linux y Termux no cambia nada.
LECTURA_ADAPTADA = adaptar_contexto_ligero()

BENCHMARKS = CONTEXTO / "benchmarks"
TAREAS_BENCHMARK = ("tasks_v35_reales.json", "tasks_v34_reales.json", "tasks_independientes.json")


class Grafo:
    """Índice de código y grafo de tareas de Contexto Ligero en una base SQLite propia del laboratorio."""

    def __init__(self, ruta_db: Path):
        self.db = index.connect(str(ruta_db))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()

    def cerrar(self):
        self.db.close()

    # --- código ---------------------------------------------------------------------------------------------
    def indexar(self, raiz: Path) -> dict:
        return index.scan(Path(raiz), self.db)

    def recuperar(self, consulta: str, limite: int = 8) -> list:
        r = retrieval.retrieve_detailed(self.db, consulta, limite)
        return [{"ruta": x["path"], "sha256": x["sha256"], "simbolos": [s["name"] for s in x.get("symbols", [])]}
                for x in r["results"]]

    def paquete(self, raiz: Path, consulta: str, presupuesto: int = 2000) -> dict:
        p = packets.build_packet(Path(raiz), self.db, consulta, presupuesto)
        return {"texto": p["text"], "metricas": p["metrics"], "omisiones": p.get("omissions"),
                "cobertura": p.get("coverage")}

    def dependencias(self, semillas: list, profundidad: int = 2) -> dict:
        return dependencies.dependency_plan(self.db, semillas, max_depth=profundidad)

    # --- tareas y decisiones desde la traza ---------------------------------------------------------------------
    def _tarea(self, nodo: str, titulo: str, estado: str, criterios) -> None:
        self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?)",
                        (nodo, titulo[:500], estado, T.canonico(criterios)))

    def importar_traza(self, traza: T.Traza) -> dict:
        """Idempotente: volver a importar no duplica nodos ni aristas."""
        cuenta = {"tareas": 0, "decisiones": 0, "aristas": 0}

        def arista(a, b, tipo):
            antes = self.db.total_changes
            index.edge(self.db, a, b, tipo)          # valida el tipo y rechaza ciclos de depends_on
            cuenta["aristas"] += self.db.total_changes - antes

        for o in traza.filas("objetivos"):
            self._tarea(f"obj:{o['id']}", o["titulo"] or o["id"], "active", json.loads(o["criterios"]))
            cuenta["tareas"] += 1
        for e in traza.filas("ejecuciones"):
            eid = e["id"]
            res = traza.filas("resultados", ejecucion_id=eid)
            self._tarea(f"ejec:{eid}", f"ejecución {eid} ({e['naturaleza']}, {e['backend']})",
                        "done" if res else "active", {"resultado": res[0]["resultado"] if res else None})
            cuenta["tareas"] += 1
            arista(f"ejec:{eid}", f"obj:{e['objetivo_id']}", "depends_on")
            for d in traza.filas("decisiones", ejecucion_id=eid):
                self.db.execute("INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?)",
                                (f"dec:{d['id']}", f"ejec:{eid}", f"{d['tipo']} (agente {d['agente'] or '—'})",
                                 f"traza_v3:{d['id']}"))
                cuenta["decisiones"] += 1
            versiones = sorted({c["version"] for c in traza.filas("cambios", ejecucion_id=eid)})
            for v in versiones:
                arista(f"ejec:{eid}", f"ver:{eid}/v{v}", "relates_to")
                if v - 1 in versiones:
                    arista(f"ver:{eid}/v{v}", f"ver:{eid}/v{v - 1}", "depends_on")
            for x in traza.filas("experiencias", ejecucion_id=eid):
                arista(f"exp:{x['agente']}/{x['recuerdo_id']}", f"ejec:{eid}", "relates_to")
        self.db.commit()
        return cuenta

    def vecinos(self, nodo: str) -> dict:
        salientes = self.db.execute("SELECT dst, kind FROM edges WHERE src = ? ORDER BY dst", (nodo,)).fetchall()
        entrantes = self.db.execute("SELECT src, kind FROM edges WHERE dst = ? ORDER BY src", (nodo,)).fetchall()
        return {"salientes": [list(x) for x in salientes], "entrantes": [list(x) for x in entrantes]}


# --- medición frente a oráculos prerregistrados -----------------------------------------------------------------
def tareas_benchmark(raiz_src: Path) -> tuple:
    """Tareas de Contexto Ligero aplicables a `raiz_src`.

    Los oráculos citan `src/eq2/...`, y se traducen a rutas relativas a `raiz_src` (`eq2/...`). Solo se conservan
    los pares (archivo, símbolo) cuyo archivo existe y define ese símbolo (`def`/`class`) en esta versión; los
    demás se cuentan como descartados, sin ocultarlos.
    """
    tareas, descartados = [], []
    for nombre in TAREAS_BENCHMARK:
        datos = json.loads((BENCHMARKS / nombre).read_text(encoding="utf-8"))
        for t in datos["tasks"] if isinstance(datos, dict) else datos:
            relevantes = []
            for ruta, simbolo in t.get("relevant", []):
                rel = ruta[4:] if ruta.startswith("src/") else ruta
                f = Path(raiz_src) / rel
                nombre_corto = simbolo.split(".")[-1]
                if f.is_file() and re.search(rf"^\s*(def|class)\s+{re.escape(nombre_corto)}\b",
                                             f.read_text(encoding="utf-8", errors="replace"), re.M):
                    relevantes.append((rel, simbolo))
                else:
                    descartados.append(f"{nombre}:{t['id']}:{ruta}::{simbolo}")
            if relevantes:
                tareas.append({"id": f"{nombre}:{t['id']}", "consulta": t["query"], "relevantes": relevantes})
    return tareas, descartados


def _ingenua(raiz_src: Path, consulta: str) -> list:
    """Línea de comparación: archivos ordenados por número de apariciones de los términos de la consulta."""
    terminos = [w for w in re.findall(r"\w+", consulta.lower()) if len(w) > 2]
    puntos = []
    for f in sorted(Path(raiz_src).rglob("*.py")):
        texto = f.read_text(encoding="utf-8", errors="replace").lower()
        n = sum(texto.count(t) for t in terminos)
        if n:
            puntos.append((-n, f.relative_to(raiz_src).as_posix()))
    return [r for _, r in sorted(puntos)]


def medir(grafo: Grafo, raiz_src: Path, ks=(1, 3, 5)) -> dict:
    """Recall@k de archivos relevantes: Contexto Ligero frente a la línea ingenua, tarea por tarea."""
    tareas, descartados = tareas_benchmark(raiz_src)
    filas = []
    for t in tareas:
        relevantes = {r for r, _ in t["relevantes"]}
        ctx = []
        for x in grafo.recuperar(t["consulta"], 12):
            if x["ruta"] not in ctx:
                ctx.append(x["ruta"])
        ing = _ingenua(raiz_src, t["consulta"])
        fila = {"id": t["id"], "relevantes": sorted(relevantes)}
        for k in ks:
            fila[f"contexto@{k}"] = len(relevantes & set(ctx[:k])) / len(relevantes)
            fila[f"ingenua@{k}"] = len(relevantes & set(ing[:k])) / len(relevantes)
        filas.append(fila)
    media = {c: round(sum(f[c] for f in filas) / len(filas), 3) for c in filas[0] if "@" in c} if filas else {}
    return {"tareas": len(filas), "descartados": descartados, "media": media, "por_tarea": filas}
