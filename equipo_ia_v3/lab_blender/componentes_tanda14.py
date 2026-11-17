"""Banco de Blender · COMPONENTES y BIBLIOTECA PERSONAL (tanda 14): coche de Fórmula 1 y kart.

Cada cerebro tiene su biblioteca (`<biblioteca>/<modelo>/<componente>.json`). Un componente se diseña UNA vez:
1. el cerebro escribe su **ficha** ANTES de construirlo: para qué sirve y qué caja total ocupará (su preregistro);
2. el programa lo construye solo, en Blender, y comprueba lo que pide la tarea + que cumple su ficha + que todas sus
   piezas están unidas;
3. si se aprueba, entra en la biblioteca con la fecha, la tarea, lo comprobado y una imagen renderizada; un rediseño
   se guarda como versión nueva sin borrar la anterior.
Cuando una tarea pide un componente que ya está en su biblioteca, el cerebro decide si lo REUTILIZA (se comprueba
contra lo pedido; si no encaja se le dice en qué) o lo REDISEÑA. Después monta el conjunto por fases (piezas →
relaciones) usando sus componentes como piezas («Rueda_DI» = una instancia de «rueda»), más cuñas, tubos y cajas.

    py -B -X utf8 eq3/lanzador_eq2.py lab_blender/componentes.py ejecutar <externos> <evidencia> <salida_blender> \
        --modelos qwen25 ministral3 --biblioteca <carpeta>
    py -B -X utf8 lab_blender/componentes.py informe <evidencia>
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import relacional2 as R
import banco as BB
import tareas as T
import ejecutor as EJ
import verificador as VF

INTENTOS = 3
BIBLIOTECA_DIR = Path(__file__).resolve().parents[1] / "evidencias" / "v31_lab_blender" / "biblioteca"

# --- componentes que piden las tareas (enunciado + comprobaciones con los nombres de sus piezas) -----------------------
COMPONENTES = {
    "rueda": {
        "texto": ("rueda de Fórmula 1 de tres piezas, todas cilindros tumbados en el eje x («eje»: \"x\") y con el "
                  "mismo centro: «Neumatico» de 0.66 m de diámetro y 0.38 m de ancho; «Llanta» de 0.42 m de diámetro "
                  "y 0.40 m de ancho; «Tuerca» de 0.10 m de diámetro y 0.44 m de ancho. «Neumatico» en (0, 0, 0)."),
        "comprobaciones": [("solo", ["Neumatico", "Llanta", "Tuerca"]),
                           *[("forma", n, "cilindro") for n in ("Neumatico", "Llanta", "Tuerca")],
                           ("dimensiones", "Neumatico", (0.38, 0.66, 0.66)), ("dimensiones", "Llanta", (0.40, 0.42, 0.42)),
                           ("dimensiones", "Tuerca", (0.44, 0.10, 0.10)), ("centro", "Neumatico", (0, 0, 0)),
                           ("concentricos", "Neumatico", "Llanta"), ("concentricos", "Neumatico", "Tuerca")]},
    "aleron_delantero": {
        "texto": ("alerón delantero: «Plano», caja de 1.6 × 0.35 × 0.04 m en (0, 0, 0); «Placa_I» y «Placa_D», cajas "
                  "de 0.03 × 0.4 × 0.12 m pegadas a cada extremo del plano (x negativa y positiva), centradas en él; "
                  "«Soporte», caja de 0.1 × 0.1 × 0.1 m justo encima del plano, centrado y tocándolo."),
        "comprobaciones": [("solo", ["Plano", "Placa_I", "Placa_D", "Soporte"]),
                           ("dimensiones", "Plano", (1.6, 0.35, 0.04)), ("dimensiones", "Placa_I", (0.03, 0.4, 0.12)),
                           ("dimensiones", "Placa_D", (0.03, 0.4, 0.12)), ("dimensiones", "Soporte", (0.1, 0.1, 0.1)),
                           ("centro", "Plano", (0, 0, 0)), ("a_un_lado", "Placa_I", "Plano", -1),
                           ("a_un_lado", "Placa_D", "Plano", 1), ("toca", "Placa_I", "Plano"),
                           ("toca", "Placa_D", "Plano"), ("simetricos", "Placa_I", "Placa_D"),
                           ("encima", "Soporte", "Plano"), ("toca", "Soporte", "Plano"),
                           ("centro", "Soporte", (0, 0, 0.07))]},
    "aleron_trasero": {
        "texto": ("alerón trasero: «Plano», caja de 1.0 × 0.3 × 0.05 m en (0, 0, 0); «Placa_I» y «Placa_D», cajas de "
                  "0.03 × 0.45 × 0.5 m pegadas a cada extremo del plano, centradas en él; «Soporte», caja de "
                  "0.06 × 0.1 × 0.5 m justo debajo del plano, centrado y tocándolo."),
        "comprobaciones": [("solo", ["Plano", "Placa_I", "Placa_D", "Soporte"]),
                           ("dimensiones", "Plano", (1.0, 0.3, 0.05)), ("dimensiones", "Placa_I", (0.03, 0.45, 0.5)),
                           ("dimensiones", "Placa_D", (0.03, 0.45, 0.5)), ("dimensiones", "Soporte", (0.06, 0.1, 0.5)),
                           ("centro", "Plano", (0, 0, 0)), ("a_un_lado", "Placa_I", "Plano", -1),
                           ("a_un_lado", "Placa_D", "Plano", 1), ("toca", "Placa_I", "Plano"),
                           ("toca", "Placa_D", "Plano"), ("simetricos", "Placa_I", "Placa_D"),
                           ("encima", "Plano", "Soporte"), ("toca", "Soporte", "Plano"),
                           ("centro", "Soporte", (0, 0, -0.275))]},
}

# --- tareas de montaje -------------------------------------------------------------------------------------------------
RUEDAS = {"DI": (-0.95, -1.1), "DD": (0.95, -1.1), "TI": (-0.95, 1.2), "TD": (0.95, 1.2)}
PARTES = {c: [x[1] for x in v["comprobaciones"] if x[0] == "solo"][0] for c, v in COMPONENTES.items()}
F1_OBJ = (["Chasis", "Morro", "Cabina", "Motor", "Ponton_I", "Ponton_D"]
          + [f"Rueda_{w}_{p}" for w in RUEDAS for p in PARTES["rueda"]]
          + [f"Aleron_D_{p}" for p in PARTES["aleron_delantero"]] + [f"Aleron_T_{p}" for p in PARTES["aleron_trasero"]]
          + [f"Susp_{w}" for w in RUEDAS])
T15 = {
    "componentes": ["rueda", "aleron_delantero", "aleron_trasero"],
    "enunciado": (
        "Monta un coche de Fórmula 1 con tus componentes. El coche mira hacia y negativa; el suelo es z = 0.\n"
        "- «Chasis»: caja de 0.7 × 3.0 × 0.35 m con centro en (0, 0, 0.35).\n"
        "- «Morro»: cuña de 0.4 × 1.0 × 0.3 m delante del chasis, tocándolo y a su altura (la cuña baja hacia "
        "delante).\n"
        "- «Cabina»: caja de 0.5 × 0.8 × 0.25 m encima del chasis, centrada en x, con su centro 0.2 m por detrás "
        "(y positiva) del centro del chasis.\n"
        "- «Motor»: caja de 0.5 × 1.0 × 0.4 m encima del chasis, centrado en x, con su centro 1.1 m por detrás del "
        "centro del chasis (queda justo detrás de la cabina, tocándola).\n"
        "- «Ponton_I» y «Ponton_D»: cajas de 0.35 × 1.2 × 0.3 m pegadas a cada lado del chasis, a su altura, con su "
        "centro 0.3 m por detrás del centro del chasis.\n"
        "- Cuatro ruedas (componente «rueda»): «Rueda_DI» y «Rueda_DD» delanteras (centro en y = -1.1), «Rueda_TI» y "
        "«Rueda_TD» traseras (y = 1.2), en x = -0.95 las «_I» y x = 0.95 las «_D», apoyadas en el suelo.\n"
        "- «Aleron_D» (componente «aleron_delantero»): justo debajo del morro, tocándolo, desplazado 0.3 m hacia "
        "delante.\n"
        "- «Aleron_T» (componente «aleron_trasero»): encima del motor, tocándolo, desplazado 0.4 m hacia atrás.\n"
        "- Cuatro suspensiones, tubos de 0.05 m de diámetro: «Susp_DI», «Susp_DD», «Susp_TI» y «Susp_TD», cada una "
        "desde su rueda hasta el chasis.\n"
        "- Todo cuelga de «Chasis»."),
    "comprobaciones": [
        ("solo", F1_OBJ), ("dimensiones", "Chasis", (0.7, 3.0, 0.35)), ("centro", "Chasis", (0, 0, 0.35)),
        ("forma", "Morro", "cuna"), ("dimensiones", "Morro", (0.4, 1.0, 0.3)), ("delante_de", "Morro", "Chasis"),
        ("toca", "Morro", "Chasis"), ("centro", "Morro", (0, -2.0, 0.35)),
        ("encima", "Cabina", "Chasis"), ("toca", "Cabina", "Chasis"), ("centro", "Cabina", (0, 0.2, 0.65)),
        ("encima", "Motor", "Chasis"), ("toca", "Motor", "Cabina"), ("centro", "Motor", (0, 1.1, 0.725)),
        ("a_un_lado", "Ponton_I", "Chasis", -1), ("a_un_lado", "Ponton_D", "Chasis", 1), ("toca", "Ponton_I", "Chasis"),
        ("simetricos", "Ponton_I", "Ponton_D"), ("centro", "Ponton_I", (-0.525, 0.3, 0.35)),
        *[c for w, (x, y) in RUEDAS.items() for c in (
            ("centro", f"Rueda_{w}_Neumatico", (x, y, 0.33)), ("apoyado", f"Rueda_{w}_Neumatico"),
            ("forma", f"Rueda_{w}_Neumatico", "cilindro"), ("dimensiones", f"Rueda_{w}_Neumatico", (0.38, 0.66, 0.66)),
            ("concentricos", f"Rueda_{w}_Neumatico", f"Rueda_{w}_Tuerca"),
            ("toca", f"Susp_{w}", "Chasis"), ("toca", f"Susp_{w}", f"Rueda_{w}_Neumatico"),
            ("forma", f"Susp_{w}", "cilindro"))],
        ("simetricos", "Rueda_DI_Neumatico", "Rueda_DD_Neumatico"), ("simetricos", "Rueda_TI_Neumatico", "Rueda_TD_Neumatico"),
        ("centro", "Aleron_D_Plano", (0, -2.3, 0.08)), ("toca", "Aleron_D_Soporte", "Morro"),
        ("centro", "Aleron_T_Plano", (0, 1.5, 1.45)), ("toca", "Aleron_T_Soporte", "Motor"),
        ("sin_solapes", ["Chasis", "Morro", "Cabina", "Motor", "Ponton_I", "Ponton_D", "Aleron_D_Plano",
                         "Aleron_T_Plano", *[f"Rueda_{w}_Neumatico" for w in RUEDAS]]),
        *[("desciende", n, "Chasis") for n in F1_OBJ if n != "Chasis"]]}
KART_RUEDAS = {"DI": (-0.82, -0.7), "DD": (0.82, -0.7), "TI": (-0.82, 0.7), "TD": (0.82, 0.7)}
KART_OBJ = (["Bastidor", "Asiento", "Volante", "Columna"]
            + [f"Rueda_{w}_{p}" for w in KART_RUEDAS for p in PARTES["rueda"]])
T16 = {
    "componentes": ["rueda"],
    "enunciado": (
        "Monta un kart con tus componentes. Mira hacia y negativa; el suelo es z = 0.\n"
        "- «Bastidor»: caja de 1.2 × 2.0 × 0.1 m con centro en (0, 0, 0.33).\n"
        "- Cuatro ruedas (componente «rueda»): «Rueda_DI», «Rueda_DD» (y = -0.7) y «Rueda_TI», «Rueda_TD» (y = 0.7), "
        "pegadas por fuera a cada lado del bastidor (las «_I» en x negativa) y a su altura.\n"
        "- «Asiento»: caja de 0.5 × 0.5 × 0.4 m encima del bastidor, centrado en x, con su centro 0.3 m por detrás "
        "(y positiva) del centro del bastidor.\n"
        "- «Volante»: cilindro de 0.3 m de diámetro y 0.04 m de grueso, de canto («eje»: \"y\"), con centro en "
        "(0, -0.4, 0.75).\n"
        "- «Columna»: tubo de 0.04 m de diámetro desde el volante hasta el bastidor.\n"
        "- Todo cuelga de «Bastidor»."),
    "comprobaciones": [
        ("solo", KART_OBJ), ("dimensiones", "Bastidor", (1.2, 2.0, 0.1)), ("centro", "Bastidor", (0, 0, 0.33)),
        *[c for w, (x, y) in KART_RUEDAS.items() for c in (
            ("centro", f"Rueda_{w}_Neumatico", (x, y, 0.33)), ("apoyado", f"Rueda_{w}_Neumatico"),
            ("toca", f"Rueda_{w}_Tuerca", "Bastidor"), ("concentricos", f"Rueda_{w}_Neumatico", f"Rueda_{w}_Llanta"))],
        ("simetricos", "Rueda_DI_Neumatico", "Rueda_DD_Neumatico"),
        ("encima", "Asiento", "Bastidor"), ("centro", "Asiento", (0, 0.3, 0.58)),
        ("forma", "Volante", "cilindro"), ("dimensiones", "Volante", (0.3, 0.04, 0.3)),
        ("centro", "Volante", (0, -0.4, 0.75)), ("toca", "Columna", "Volante"), ("toca", "Columna", "Bastidor"),
        ("sin_solapes", ["Bastidor", "Asiento", "Volante", *[f"Rueda_{w}_Neumatico" for w in KART_RUEDAS]]),
        *[("desciende", n, "Bastidor") for n in KART_OBJ if n != "Bastidor"]]}
T.TAREAS.setdefault("T15", T15)
T.TAREAS.setdefault("T16", T16)
TAREAS_C = ("T15", "T16")

SISTEMA_COMP = R.SISTEMA + (
    "\n\nCOMPONENTES. Un componente es un grupo de piezas que se diseña una vez y se reutiliza. Su ficha es "
    "{\"componente\": {\"nombre\": …, \"para_que\": \"una frase\", \"medidas\": [x, y, z], \"piezas\": […], "
    "\"relaciones\": […]}}. \"medidas\" es la caja TOTAL que ocupará el componente entero: decláralo antes de "
    "construirlo (es tu compromiso; se comprueba). Coloca la pieza principal con [\"centro\", …, 0, 0, 0].\n"
    "Para usar un componente de tu biblioteca en un montaje: {\"nombre\": \"Rueda_DI\", \"componente\": \"rueda\", "
    "\"padre\": …} (\"espejo\": true lo refleja en x). Se coloca con relaciones como una pieza más, usando su caja "
    "total; sus piezas se llamarán «Rueda_DI_Neumatico», etc.\n"
    "Otras piezas: \"forma\": \"cuna\" (rampa que baja hacia y negativa), \"rotacion\": [gx, gy, gz] en grados, y "
    "tubos {\"nombre\": …, \"forma\": \"tubo\", \"diametro\": d, \"desde\": A, \"hasta\": B} (del centro de A al punto "
    "más cercano de B; no llevan relaciones).")


# --- biblioteca ----------------------------------------------------------------------------------------------------------
def carpeta(modelo: str) -> Path:
    return Path(BIBLIOTECA_DIR) / modelo


def cargar(modelo: str) -> dict:
    """{nombre: ficha + piezas resueltas + caja} de la última versión de cada componente aprobado."""
    out = {}
    c = carpeta(modelo)
    if c.is_dir():
        for f in sorted(c.glob("*.json")):
            ficha = json.loads(f.read_text(encoding="utf-8"))
            if ficha["nombre"] not in out or ficha["version"] > out[ficha["nombre"]]["version"]:
                out[ficha["nombre"]] = {**ficha, **R.resolver_componente(ficha)}
    return out


def indice(bib: dict) -> str:
    if not bib:
        return "TU BIBLIOTECA: vacía."
    return "TU BIBLIOTECA (componentes aprobados):\n" + "\n".join(
        f"- «{n}» v{c['version']}: {c.get('para_que', '')}; ocupa {[round(v, 3) for v in c['caja']]} m; piezas: "
        f"{', '.join(c['partes'])}" for n, c in bib.items())


def guardar(modelo: str, ficha: dict, verificado: dict, salida_blender: Path) -> dict:
    c = carpeta(modelo)
    c.mkdir(parents=True, exist_ok=True)
    version = 1 + max((json.loads(f.read_text(encoding="utf-8"))["version"] for f in c.glob(f"{ficha['nombre']}_v*.json")),
                      default=0)
    entrada = {"nombre": ficha["nombre"], "para_que": ficha.get("para_que", ""), "medidas": ficha["medidas"],
               "piezas": ficha["piezas"], "relaciones": ficha.get("relaciones", []), "version": version,
               "autor": modelo, "verificado": verificado}
    destino = c / f"{ficha['nombre']}_v{version}.json"
    destino.write_text(json.dumps(entrada, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    try:                                                 # imagen del componente aprobado (para verlo; no decide nada)
        r = EJ.ejecutar(R.generar(entrada), Path(salida_blender) / "biblioteca" / modelo / f"{ficha['nombre']}_v{version}",
                        render={"motor": "BLENDER_EEVEE", "resolucion": [640, 360], "video": False, "fotogramas": [1]},
                        tiempo_s=120)
        png = Path(r.get("carpeta") or "") / "fotograma_0001.png"
        if not png.is_file():
            png = next((Path(salida_blender) / "biblioteca" / modelo / f"{ficha['nombre']}_v{version}").rglob("*.png"), None)
        if png and png.is_file():
            (c / f"{ficha['nombre']}_v{version}.png").write_bytes(png.read_bytes())
    except Exception:                                    # sin imagen no se pierde el componente
        pass
    return entrada


# --- comprobación de un componente ---------------------------------------------------------------------------------------
def comprobar_componente(id_: str, nombre: str, ficha: dict, carpeta_b: Path) -> tuple:
    """(veredicto, texto de vuelta). Lo que pide la tarea + que cumple su ficha + piezas unidas."""
    script = R.generar({"piezas": ficha["piezas"], "relaciones": ficha.get("relaciones", [])})
    med = ficha.get("medidas")
    if not isinstance(med, list) or len(med) != 3:
        raise R.ErrorRel("la ficha necesita \"medidas\": [x, y, z], la caja total que ocupará (tu preregistro)")
    nombres = [p["nombre"] for p in ficha["piezas"]]
    cs = COMPONENTES[nombre]["comprobaciones"] + [("caja_total", nombres, tuple(med)), ("conectado", nombres)]
    r, v = R._probar(id_, cs, script, carpeta_b)
    pistas = R.como_arreglar(T.TAREAS[id_], v) if not v["aprobado"] else []
    if any(c["comprobacion"] == "caja_total" and not c["cumple"] for c in v.get("comprobaciones", [])):
        pistas.append("tu ficha no coincide con lo construido: corrige \"medidas\" o las piezas")
    return r, v, v["texto"] + ("\n\nCÓMO ARREGLARLO:\n- " + "\n- ".join(pistas) if pistas else "")


# --- bucle ---------------------------------------------------------------------------------------------------------------
FASES_MONTAJE = ["piezas", "relaciones"]


def _a_instancias(pistas: list, d: dict) -> list:
    """En los avisos, «Rueda_DI_Neumatico» → «Rueda_DI»: las relaciones se escriben sobre la instancia."""
    inst = {p["nombre"]: p["componente"] for p in d.get("piezas") or [] if isinstance(p, dict) and p.get("componente")}
    out = []
    for h in pistas:
        for n, c in inst.items():
            for parte in PARTES.get(c, []):
                h = h.replace(f"{n}_{parte}", n)
        if h not in out:
            out.append(h)
    if inst and out:
        out.append("las piezas de un componente («Rueda_DI_Neumatico»…) se mueven con su instancia («Rueda_DI»): "
                   "escribe las relaciones sobre la instancia")
    return out


def _filas(filas, modelo, id_, fase):
    return [f for f in filas if f["modelo"] == modelo and f["tarea"] == id_ and f.get("fase") == fase
            and f.get("tipo") != "final"]


def _msg(u: str) -> list:
    return [{"role": "system", "content": SISTEMA_COMP}, {"role": "user", "content": u}]


def _guardar(evidencia, fila):
    with (Path(evidencia) / "peticiones.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


def _pedir(completar, msgs):
    t0 = time.monotonic()
    texto, tokens, fin = completar(msgs, BB.TOKENS)
    m = R._JSON.search(texto or "")
    return texto, tokens, fin, round(time.monotonic() - t0, 2), (m.group(1) if m else (texto or "")).strip()


def paso_componente(modelo, id_, nombre, evidencia, salida_blender, completar) -> bool:
    """Un intento sobre un componente. True si queda resuelto (aprobado o agotado)."""
    fase = f"comp:{nombre}"
    h = _filas(R.leer_filas(evidencia), modelo, id_, fase)
    if any(f["aprobado"] for f in h) or len(h) >= INTENTOS:
        return True
    bib = cargar(modelo)
    tiene = nombre in bib
    previo = h[-1] if h else None
    u = (f"TAREA (contexto):\n{T.TAREAS[id_]['enunciado']}\n\n{indice(bib)}\n\nCOMPONENTE «{nombre}»: "
         f"{COMPONENTES[nombre]['texto']}\n\n")
    if tiene and not (previo and previo.get("decision") == "reutilizar"):
        u += (f"Ya tienes «{nombre}» en tu biblioteca. Si te sirve tal cual, responde {{\"decision\": \"reutilizar\"}}; "
              f"si no, escribe una ficha nueva (rediseño) con {{\"componente\": {{…}}}}.")
    else:
        u += "Escribe su ficha: {\"componente\": {\"nombre\": …, \"para_que\": …, \"medidas\": […], \"piezas\": […], " \
             "\"relaciones\": […]}}."
    if previo:
        u += (f"\n\nTu respuesta anterior:\n```json\n{previo['respuesta']}\n```\n\nResultado:\n{previo['feedback']}\n\n"
              "Corrige y devuélvelo completo.")
    texto, tokens, fin, seg, resp = _pedir(completar, _msg(u))
    fila = {"modelo": modelo, "tarea": id_, "fase": fase, "intento": len(h) + 1, "texto": texto, "respuesta": resp,
            "tokens": tokens, "finish_reason": fin, "segundos_cerebro": seg, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
    carpeta_b = Path(salida_blender) / modelo / f"{id_}_{nombre}_i{len(h) + 1}_{int(time.time())}"
    try:
        d = R.leer_json(texto)
        if d.get("decision") == "reutilizar":
            if not tiene:
                raise R.ErrorRel(f"no tienes «{nombre}» en tu biblioteca: escribe su ficha")
            ficha = {k: bib[nombre][k] for k in ("nombre", "para_que", "medidas", "piezas", "relaciones")}
            fila["decision"] = "reutilizar"
        else:
            ficha = d.get("componente")
            if not isinstance(ficha, dict):
                raise R.ErrorRel("falta {\"componente\": {…}} (o {\"decision\": \"reutilizar\"} si ya lo tienes)")
            ficha["nombre"] = nombre
            fila["decision"] = "rediseñar" if tiene else "nuevo"
        r, v, fb = comprobar_componente(id_, nombre, ficha, carpeta_b)
        fila.update(ficha=ficha, estado=r["estado"], aprobado=v["aprobado"], cumplidas=v.get("cumplidas", 0),
                    total=v.get("total", 0), feedback=fb if not v["aprobado"] or fila["decision"] != "reutilizar" else fb)
        if v["aprobado"] and fila["decision"] != "reutilizar":
            fila["guardado"] = guardar(modelo, ficha, {"fecha": fila["fecha"], "tarea": id_, "cumplidas": v["cumplidas"],
                                                       "total": v["total"]}, salida_blender)["version"]
        if not v["aprobado"] and fila["decision"] == "reutilizar":
            fila["feedback"] = f"Tu «{nombre}» de la biblioteca NO encaja con lo pedido aquí:\n{fb}\n\nRediséñalo."
    except R.ErrorRel as err:
        fila.update(ficha=None, estado="ERROR_RESOLVEDOR", aprobado=False, cumplidas=0, total=0,
                    feedback=f"El programa no pudo construir el componente: {err}")
    _guardar(evidencia, fila)
    return False


def correr(modelo, ids, evidencia, salida_blender, completar, parar=lambda: False) -> str:
    evidencia = Path(evidencia)
    for id_ in (ids or TAREAS_C):
        if any(f["modelo"] == modelo and f["tarea"] == id_ and f.get("tipo") == "final" for f in R.leer_filas(evidencia)):
            continue
        for nombre in T.TAREAS[id_]["componentes"]:     # 1) componentes (reutilizar o diseñar)
            while not paso_componente(modelo, id_, nombre, evidencia, salida_blender, completar):
                if parar():
                    return "parado"
        bib = cargar(modelo)
        faltan = [c for c in T.TAREAS[id_]["componentes"] if not any(
            f["aprobado"] for f in _filas(R.leer_filas(evidencia), modelo, id_, f"comp:{c}"))]
        acum = {}
        for k, fase in enumerate(FASES_MONTAJE, 1):      # 2) montaje por fases
            if faltan:
                break
            while True:
                h = _filas(R.leer_filas(evidencia), modelo, id_, fase)
                ok = next((f for f in h if f["aprobado"]), None)
                if ok:
                    acum[fase] = ok["parte"][fase]
                    break
                if len(h) >= INTENTOS:
                    break
                if parar():
                    return "parado"
                previo = h[-1] if h else None
                u = (f"TAREA:\n{T.TAREAS[id_]['enunciado']}\n\n{indice(bib)}"
                     + (f"\n\nYA APROBADO (no lo repitas):\n```json\n{json.dumps(acum, ensure_ascii=False)}\n```" if acum else "")
                     + f"\n\nFASE {k} de {len(FASES_MONTAJE)}: {R.FASES[fase]}")
                if previo:
                    u += (f"\n\nTu respuesta anterior:\n```json\n{previo['respuesta']}\n```\n\nResultado:\n"
                          f"{previo['feedback']}\n\nCorrige y devuélvelo completo.")
                texto, tokens, fin, seg, resp = _pedir(completar, _msg(u))
                fila = {"modelo": modelo, "tarea": id_, "fase": fase, "intento": len(h) + 1, "texto": texto,
                        "respuesta": resp, "tokens": tokens, "finish_reason": fin, "segundos_cerebro": seg,
                        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
                try:
                    d = R.leer_json(texto)
                    if fase not in d:
                        raise R.ErrorRel(f"falta la clave \"{fase}\": {R.FASES[fase]}")
                    completo = {**acum, fase: d[fase]}
                    script = R.generar(completo, sin_relaciones_ok=(fase == "piezas"), biblioteca=bib)
                    cs = R.comprobaciones_fase(id_, fase)
                    r, v = R._probar(id_, cs, script, Path(salida_blender) / modelo / f"{id_}_{fase}_i{len(h) + 1}_{int(time.time())}")
                    pistas = _a_instancias(R.como_arreglar(T.TAREAS[id_], v), completo) if not v["aprobado"] else []
                    fila.update(parte={fase: d[fase]}, script=script, estado=r["estado"], aprobado=v["aprobado"],
                                cumplidas=v.get("cumplidas", 0), total=v.get("total", len(cs)),
                                feedback=v["texto"] + ("\n\nCÓMO ARREGLARLO:\n- " + "\n- ".join(pistas) if pistas else ""))
                except R.ErrorRel as err:
                    fila.update(parte=None, script=None, estado="ERROR_RESOLVEDOR", aprobado=False, cumplidas=0,
                                total=0, feedback=f"El programa no pudo construir la escena: {err}")
                _guardar(evidencia, fila)
            if fase not in acum:
                break
        # 3) cierre: lo aprobado, con TODAS las comprobaciones
        tot = len(T.TAREAS[id_]["comprobaciones"])
        res = {"aprobado": False, "cumplidas": 0, "total": tot, "estado": "SIN_ESCENA", "feedback": ""}
        script = None
        if acum.get("piezas"):
            try:
                script = R.generar(acum, sin_relaciones_ok=True, biblioteca=bib)
            except R.ErrorRel:
                script = None
        if script:
            r, v = R._probar(id_, T.TAREAS[id_]["comprobaciones"], script,
                             Path(salida_blender) / modelo / f"{id_}_final_{int(time.time())}")
            res = {"aprobado": v["aprobado"], "cumplidas": v.get("cumplidas", 0), "total": v.get("total", tot),
                   "estado": r["estado"], "feedback": v["texto"]}
        _guardar(evidencia, {"modelo": modelo, "tarea": id_, "tipo": "final", "componentes_faltan": faltan,
                             "fases_aprobadas": len(acum), "json": acum, "script": script, **res,
                             "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return "completo"


def pendientes(modelo, ids, evidencia) -> bool:
    filas = R.leer_filas(evidencia)
    return any(not any(f["modelo"] == modelo and f["tarea"] == i and f.get("tipo") == "final" for f in filas)
               for i in (ids or TAREAS_C))


def informe(evidencia: Path) -> str:
    filas = R.leer_filas(evidencia)
    L = ["# Banco de Blender · componentes y biblioteca: informe", "",
         "| modelo | tarea | resultado final | componentes (decisión: intentos) | montaje | llamadas |",
         "|---|---|---|---|---|---|"]
    for m in dict.fromkeys(f["modelo"] for f in filas):
        for id_ in TAREAS_C:
            fin = next((f for f in filas if f["modelo"] == m and f["tarea"] == id_ and f.get("tipo") == "final"), None)
            if not fin:
                continue
            hs = [f for f in filas if f["modelo"] == m and f["tarea"] == id_ and f.get("tipo") != "final"]
            comp = []
            for c in T.TAREAS[id_]["componentes"]:
                hc = [f for f in hs if f.get("fase") == f"comp:{c}"]
                ok = next((f for f in hc if f["aprobado"]), None)
                comp.append(f"{c}: {(ok or (hc[-1] if hc else {})).get('decision', '—')} "
                            f"{'✓' if ok else '✗'} {len(hc)}")
            mont = " · ".join(f"{f['fase'][:4]}:{f['estado']}" for f in hs if not f["fase"].startswith("comp:"))
            L.append(f"| {m} | {id_} | {'APROBADO' if fin['aprobado'] else 'no'} ({fin['cumplidas']}/{fin['total']}) | "
                     f"{'; '.join(comp)} | {mont or '—'} | {len(hs)} |")
    texto = "\n".join(L) + "\n"
    (Path(evidencia) / "INFORME.md").write_text(texto, encoding="utf-8", newline="\n")
    return texto


def main(argv=None) -> int:
    global BIBLIOTECA_DIR
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("ejecutar", "informe"))
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--modelos", nargs="+", default=["qwen25", "ministral3"])
    ap.add_argument("--biblioteca", default=str(BIBLIOTECA_DIR))
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--permitir_uso", action="store_true", help="el PC se usa a la vez: no mira teclado/ratón (VRAM, GPU y térmica siguen)")
    a = ap.parse_args(argv)
    if a.orden == "informe":
        print(informe(Path(a.rutas[0])))
        return 0
    BIBLIOTECA_DIR = Path(a.biblioteca)
    r = BB.ejecutar(Path(a.rutas[0]), Path(a.rutas[1]), Path(a.rutas[2]), tuple(a.modelos), list(TAREAS_C),
                    a.reanudar, correr=correr, pendientes_fn=pendientes,
                    permitir_uso=a.permitir_uso)
    print(json.dumps({k: r.get(k) for k in ("inicio", "fin", "abortada")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
