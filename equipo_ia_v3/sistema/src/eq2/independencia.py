"""V2-E.6: señales DETERMINISTAS de (falta de) independencia en una deliberación.

Los tres agentes son el MISMO modelo interpretando roles distintos, así que la independencia no se puede
dar por supuesta. Este módulo no decide quién tiene razón ni castiga a nadie: detecta patrones
observables en los textos y los votos y los informa como advertencias (no cambian el recuento ni el
nivel de fiabilidad, igual que las demás advertencias de V2-C/V2-E.5).

Señales:
  revision_eco_de_propuesta        la revisión de A3 reproduce en gran parte el texto de la propuesta
  revision_asume_autor_correcto    A3 se apoya en la autoridad del autor («A1 tiene razón», «confío en A1»)
  aprobacion_sin_comprobacion      A3 escribe SIN OBJECIONES sin decir qué comprobó y vota aprobar
  replica_repite_propuesta         la réplica es (casi) la propuesta pese a haber objeciones
  respuesta_repetida               dos fases distintas tienen el mismo texto normalizado
  razones_de_voto_similares        dos razones de voto muy parecidas (Jaccard de palabras)
  votos_identicos                  las tres razones son idénticas
  autovoto_divergente              A1 aprueba su propuesta y los otros dos la rechazan o piden cambios
  decision_depende_del_autor       sin el voto de A1 el resultado cambiaría (protocolo V2-D)

IMPORTANTE: la SIMILITUD NO PRUEBA COPIA. Dos agentes que razonan bien sobre la misma tarea pueden
coincidir. Las señales de similitud se marcan «indicio», nunca «copia».
"""
from __future__ import annotations

import re
import unicodedata

from . import protocolo

UMBRAL_ECO = 0.6            # fracción de 5-gramas de la revisión presentes en la propuesta
UMBRAL_REPETICION = 0.9
UMBRAL_RAZONES = 0.7        # Jaccard de palabras entre razones de voto
MIN_PALABRAS = 4
_VACIAS = set("""el la los las un una unos unas de del al y o u a en con por para que es son se no lo le les
su sus este esta esto ese esa como mas pero sin sobre muy ya hay ser fue the and for with this that""".split())
_AUTORIDAD = [re.compile(p, re.IGNORECASE) for p in (
    r"\b(a1|el programador|el autor)\s+(tiene|ten[ií]a)\s+raz[oó]n",
    r"\b(a1|el programador|el autor)\s+est[aá]\s+en\s+lo\s+cierto",
    r"\bconf[ií]o\s+en\s+(a1|el programador|el autor|la propuesta)",
    r"\bcomo\s+(dice|indica|afirma|propone)\s+(a1|el programador|el autor)",
    r"\b(no|sin)\s+(hace\s+falta|necesidad\s+de)\s+(revisar|comprobar|verificar)",
    r"\bdoy\s+por\s+(buena|correcta|v[aá]lida)\s+la\s+propuesta",
)]
_SIN_OBJ = re.compile(r"SIN OBJECIONES\s*:?\s*(.*)", re.IGNORECASE)
_GENERICO = re.compile(r"^(todo\s+)?(bien|correcto|ok|nada|perfecto|parece\s+bien|est[aá]\s+bien)[.!]*$",
                       re.IGNORECASE)
_OBJ = re.compile(r"^\s*OBJECION\b", re.IGNORECASE | re.MULTILINE)
NOTA = ("señales deterministas sobre textos y votos; la similitud NO prueba copia y ninguna señal dice "
        "quién tiene razón. No cambian el recuento.")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def palabras(t: str) -> set:
    return {p for p in _norm(t).split() if len(p) >= 3 and p not in _VACIAS}


def jaccard(a: str, b: str):
    pa, pb = palabras(a), palabras(b)
    if len(pa) < MIN_PALABRAS or len(pb) < MIN_PALABRAS:
        return None                                   # demasiado corto para comparar
    return round(len(pa & pb) / len(pa | pb), 3)


def _ngramas(t: str, k: int = 5) -> set:
    w = _norm(t).split()
    return {tuple(w[i:i + k]) for i in range(len(w) - k + 1)}


def contencion(a: str, b: str, k: int = 5):
    """Fracción de k-gramas de `a` que aparecen en `b` (None si `a` es demasiado corto)."""
    ga = _ngramas(a, k)
    if len(ga) < 3:
        return None
    return round(len(ga & _ngramas(b, k)) / len(ga), 3)


def analizar(hist: dict, votos: dict | None = None, estados: dict | None = None) -> dict:
    """hist: {analisis, propuesta, revision, replica}; votos: {agente: (postura, razon)}."""
    hist = hist or {}
    votos = votos or {}
    sen, met = [], {}
    prop, rev, rep = hist.get("propuesta", "") or "", hist.get("revision", "") or "", hist.get("replica", "") or ""

    eco = contencion(rev, prop)
    met["eco_revision"] = eco
    if eco is not None and eco >= UMBRAL_ECO:
        sen.append({"tipo": "revision_eco_de_propuesta", "agentes": ["A3"], "metrica": eco, "grado": "indicio"})
    for rx in _AUTORIDAD:
        m = rx.search(rev)
        if m:
            sen.append({"tipo": "revision_asume_autor_correcto", "agentes": ["A3"], "cita": m.group(0)[:80],
                        "grado": "observado"})
            break
    m = _SIN_OBJ.search(rev)
    a3 = (votos.get("A3") or ("", ""))[0]
    if m and not _OBJ.search(rev):
        que = re.split(r"[.;\n]", m.group(1), maxsplit=1)[0].strip()      # la primera frase: «qué comprobé»
        if (len(que) < 15 or _GENERICO.match(que)) and a3 == "aprobar":
            sen.append({"tipo": "aprobacion_sin_comprobacion", "agentes": ["A3"], "detalle": que[:60] or "(vacío)",
                        "grado": "observado"})
    rep_prop = contencion(rep, prop)
    met["replica_vs_propuesta"] = rep_prop
    if _OBJ.search(rev) and rep_prop is not None and rep_prop >= UMBRAL_REPETICION:
        sen.append({"tipo": "replica_repite_propuesta", "agentes": ["A1"], "metrica": rep_prop, "grado": "indicio"})
    fases = [f for f in ("analisis", "propuesta", "revision", "replica") if _norm(hist.get(f, ""))]
    for i, a in enumerate(fases):
        for b in fases[i + 1:]:
            if _norm(hist[a]) == _norm(hist[b]) and len(_norm(hist[a])) >= 20:
                sen.append({"tipo": "respuesta_repetida", "fases": [a, b], "grado": "observado"})

    razones = {ag: (v[1] or "") for ag, v in sorted(votos.items())
               if v and (estados or {}).get(ag, "valido") == "valido"}
    ags = sorted(razones)
    met["jaccard_razones"] = {}
    for i, a in enumerate(ags):
        for b in ags[i + 1:]:
            j = jaccard(razones[a], razones[b])
            met["jaccard_razones"][f"{a}-{b}"] = j
            if j is not None and j >= UMBRAL_RAZONES:
                sen.append({"tipo": "razones_de_voto_similares", "agentes": [a, b], "metrica": j,
                            "grado": "indicio", "nota": "similitud no prueba copia"})
    norm_r = [_norm(r) for r in razones.values()]
    if len(norm_r) == 3 and len(set(norm_r)) == 1 and len(norm_r[0]) >= 10:
        sen.append({"tipo": "votos_identicos", "agentes": ags, "grado": "observado",
                    "nota": "idénticos no implica copiados; con un solo modelo es un riesgo conocido"})
    post = {ag: (v[0] if v else None) for ag, v in votos.items()}
    if post.get("A1") in ("aprobar", "aprobar_con_cambios") and all(
            post.get(x) in ("rechazar", "aprobar_con_cambios") for x in ("A2", "A3")) and \
            "rechazar" in (post.get("A2"), post.get("A3")):
        sen.append({"tipo": "autovoto_divergente", "agentes": ["A1"], "grado": "observado"})
    if votos and len(votos) == 3:
        try:
            if protocolo.depende_del_autor(votos, estados):
                sen.append({"tipo": "decision_depende_del_autor", "agentes": ["A1"], "grado": "observado"})
        except (KeyError, TypeError, ValueError):
            pass
    tipos = sorted({s["tipo"] for s in sen})
    return {"senales": sen, "tipos": tipos, "metricas": met,
            "revision_independiente": not ({"revision_eco_de_propuesta", "revision_asume_autor_correcto",
                                             "aprobacion_sin_comprobacion"} & set(tipos)),
            "nota": NOTA}
