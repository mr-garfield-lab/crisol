"""Se ejecuta DENTRO de Blender (lo lanza lab_blender/ejecutor.py; no se llama a mano).

    blender -b --factory-startup -Y --offline-mode -noaudio -P dentro_blender.py -- CONFIG.json

Abre una escena vacía (o la COPIA de un .blend), vuelve a pasar el filtro al script del cerebro, lo ejecuta con una lista
cerrada de funciones integradas y de módulos, y escribe `informe.json` con HECHOS de la escena (objetos, medidas, materiales,
posiciones en varios fotogramas). No da veredictos. Después guarda `resultado.blend` y, si se pide, fotogramas o un vídeo.
Todo lo que escribe va a la carpeta de salida de la configuración.
"""
import builtins
import hashlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

NOMBRE_SCRIPT = "script_cerebro.py"
MAX_SALIDA = 6000                                            # caracteres de print() que se conservan
MAX_OBJETOS_DETALLE = 400
# simulaciones y cachés que escriben en disco al avanzar fotogramas: si aparecen, no se mide la animación ni se renderiza
MODIFICADORES_PROHIBIDOS = {"FLUID", "OCEAN", "DYNAMIC_PAINT", "MESH_SEQUENCE_CACHE", "MESH_CACHE"}


def escribir(ruta: Path, datos: dict):
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, ruta)


def r4(v):
    return [round(float(x), 4) for x in v]


# --- ejecución del script con funciones y módulos de lista cerrada --------------------------------------------------------
def entorno(filtro, salida_texto: list) -> dict:
    def importar(nombre, globals=None, locals=None, fromlist=(), level=0):
        if level or nombre not in filtro.MODULOS:
            raise ImportError(f"módulo no permitido: {nombre}")
        return builtins.__import__(nombre, globals, locals, fromlist, level)

    def imprimir(*args, sep=" ", end="\n", **_):
        if sum(map(len, salida_texto)) < MAX_SALIDA:
            salida_texto.append(sep.join(str(a) for a in args) + end)

    permitidas = {n: getattr(builtins, n) for n in filtro.INTEGRADAS if hasattr(builtins, n)}
    permitidas |= {"__import__": importar, "print": imprimir}
    return {"__builtins__": permitidas, "__name__": "__main__"}


def linea_del_error(tb) -> int | None:
    linea = None
    for marco in traceback.extract_tb(tb):
        if marco.filename == NOMBRE_SCRIPT:
            linea = marco.lineno
    return linea


def ejecutar_script(texto: str, filtro) -> dict:
    salida_texto: list = []
    r = {"ok": False, "error": None, "linea": None}
    t0 = time.monotonic()
    try:
        exec(compile(texto, NOMBRE_SCRIPT, "exec"), entorno(filtro, salida_texto))
        r["ok"] = True
    except BaseException as e:                              # también SystemExit y KeyboardInterrupt del script
        r["error"] = f"{type(e).__name__}: {e}"[:1500]
        r["linea"] = linea_del_error(e.__traceback__) or getattr(e, "lineno", None)
        if r["linea"]:
            lineas = texto.splitlines()
            r["codigo_de_la_linea"] = lineas[r["linea"] - 1].strip()[:200] if r["linea"] <= len(lineas) else None
    r["segundos"] = round(time.monotonic() - t0, 2)
    r["salida"] = "".join(salida_texto)[:MAX_SALIDA]
    return r


# --- hechos de la escena --------------------------------------------------------------------------------------------------
def color_de(mat):
    """Los dos colores de un material: el de los nodos (el que sale en el render) y el de la vista 3D."""
    if mat is None:
        return None
    nodos = None
    if mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                nodos = r4(n.inputs["Base Color"].default_value)
                break
    return {"nodos": nodos, "vista": r4(mat.diffuse_color)}


def caja(ob_eval):
    """Caja envolvente en coordenadas del mundo: (mín, máx)."""
    p = [ob_eval.matrix_world @ Vector(c) for c in ob_eval.bound_box]
    return r4(min(v[i] for v in p) for i in range(3)), r4(max(v[i] for v in p) for i in range(3))


def fotogramas_de_muestra(sc, n: int) -> list:
    a, b = sc.frame_start, max(sc.frame_start, sc.frame_end)
    if n <= 1 or a == b:
        return [a]
    return sorted({round(a + k * (b - a) / (n - 1)) for k in range(n)})


def hechos(muestras: int, limites: dict) -> dict:
    sc = bpy.context.scene
    obs = list(sc.objects)
    h = {"fotograma_inicial": sc.frame_start, "fotograma_final": sc.frame_end,
         "fps": round(sc.render.fps / sc.render.fps_base, 3), "camara": sc.camera.name if sc.camera else None,
         "n_objetos": len(obs), "por_tipo": {}, "n_materiales": len(bpy.data.materials),
         "colecciones": [c.name for c in bpy.data.collections][:60], "objetos": [], "limites_superados": []}
    for ob in obs:
        h["por_tipo"][ob.type] = h["por_tipo"].get(ob.type, 0) + 1
    if len(obs) > limites["objetos"]:
        h["limites_superados"].append(f"{len(obs)} objetos (máximo {limites['objetos']})")
        return h
    for ob in obs:
        malos = sorted({m.type for m in ob.modifiers} & MODIFICADORES_PROHIBIDOS)
        if malos:
            h["limites_superados"].append(f"{ob.name} usa un modificador no permitido: {', '.join(malos)}")
    if h["limites_superados"]:
        return h
    actual = sc.frame_current
    sc.frame_set(sc.frame_start)
    dg = bpy.context.evaluated_depsgraph_get()
    vert_total = caras_total = 0
    detalle = obs[:MAX_OBJETOS_DETALLE]
    for ob in detalle:
        ev = ob.evaluated_get(dg)
        mn, mx = caja(ev)
        d = {"nombre": ob.name, "tipo": ob.type, "posicion": r4(ev.matrix_world.translation),
             "rotacion_grados": [round(math.degrees(a), 2) for a in ev.matrix_world.to_euler()],
             "escala": r4(ev.matrix_world.to_scale()), "dimensiones": r4(ev.dimensions), "caja_min": mn, "caja_max": mx,
             "padre": ob.parent.name if ob.parent else None, "oculto_en_render": bool(ob.hide_render),
             "materiales": [s.material.name if s.material else None for s in ob.material_slots],
             "colores": [color_de(s.material) for s in ob.material_slots],
             "modificadores": [m.type for m in ob.modifiers], "restricciones": [c.type for c in ob.constraints],
             "colecciones": [c.name for c in ob.users_collection]}
        if ob.parent and ob.parent_type == "BONE":
            d["hueso_padre"] = ob.parent_bone
        if ob.type == "ARMATURE":
            d["huesos"] = [b.name for b in ob.data.bones][:60]
            d["n_huesos"] = len(ob.data.bones)
        if ob.type in ("MESH", "CURVE", "SURFACE", "FONT", "META"):
            try:
                me = ev.to_mesh()
                d["vertices"], d["caras"] = len(me.vertices), len(me.polygons)
                vert_total += d["vertices"]
                caras_total += d["caras"]
                ev.to_mesh_clear()
            except RuntimeError:
                d["vertices"] = d["caras"] = None
        h["objetos"].append(d)
    h["vertices_total"], h["caras_total"] = vert_total, caras_total
    if vert_total > limites["vertices"]:
        h["limites_superados"].append(f"{vert_total} vértices (máximo {limites['vertices']})")
    # posiciones en varios fotogramas: así se ve si algo se mueve sin depender de cómo esté hecha la animación
    cuadros = fotogramas_de_muestra(sc, muestras)
    h["fotogramas_de_muestra"] = cuadros
    if len(cuadros) > 1 and not h["limites_superados"]:
        por_objeto = {d["nombre"]: [] for d in h["objetos"]}
        for f in cuadros:
            sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            for ob in detalle:
                ev = ob.evaluated_get(dg)
                mn, mx = caja(ev)
                por_objeto[ob.name].append({"fotograma": f, "posicion": r4(ev.matrix_world.translation),
                                            "rotacion_grados": [round(math.degrees(a), 2) for a in ev.matrix_world.to_euler()],
                                            "caja_min": mn, "caja_max": mx})
        for d in h["objetos"]:
            m = por_objeto[d["nombre"]]
            d["muestras"] = m
            d["se_mueve"] = any(max(abs(a - b) for a, b in zip(x["posicion"] + x["rotacion_grados"],
                                                                 m[0]["posicion"] + m[0]["rotacion_grados"])) > 1e-3
                                for x in m[1:])
        h["objetos_que_se_mueven"] = [d["nombre"] for d in h["objetos"] if d.get("se_mueve")]
    sc.frame_set(actual)
    cajas = [d for d in h["objetos"] if d["tipo"] in ("MESH", "CURVE", "SURFACE", "FONT", "META")]
    if cajas:
        h["caja_min"] = r4(min(d["caja_min"][i] for d in cajas) for i in range(3))
        h["caja_max"] = r4(max(d["caja_max"][i] for d in cajas) for i in range(3))
    return h


# --- render (lo hace este archivo, nunca el script del cerebro) -----------------------------------------------------------
def encuadrar(sc, h: dict) -> dict:
    """Si la escena no tiene cámara, añade una que encuadre toda la geometría (y lo anota)."""
    extra = {}
    if sc.camera is None:
        # se encuadra lo que no es un suelo (objetos planos y muy anchos), en todos los fotogramas de muestra
        geo = [d for d in h["objetos"] if d["tipo"] in ("MESH", "CURVE", "SURFACE", "FONT", "META")]
        plano = lambda d: d["dimensiones"][2] < 0.02 * max(d["dimensiones"][0], d["dimensiones"][1], 1e-9)
        cuerpos = [d for d in geo if not plano(d)] or geo
        cajas = [(m["caja_min"], m["caja_max"]) for d in cuerpos for m in d.get("muestras", [])]
        cajas += [(d["caja_min"], d["caja_max"]) for d in cuerpos]
        mn = Vector([min(c[0][i] for c in cajas) for i in range(3)]) if cajas else Vector((-1, -1, -1))
        mx = Vector([max(c[1][i] for c in cajas) for i in range(3)]) if cajas else Vector((1, 1, 1))
        centro, radio = (mn + mx) / 2, max((mx - mn).length / 2, 0.5)
        datos = bpy.data.cameras.new("LAB_camara")
        cam = bpy.data.objects.new("LAB_camara", datos)
        sc.collection.objects.link(cam)
        direccion = Vector((1.0, -1.0, 0.6)).normalized()
        # el ángulo de la cámara es el del lado ancho: en horizontal manda el vertical, que es más estrecho
        proporcion = min(1.0, sc.render.resolution_y / max(sc.render.resolution_x, 1))
        medio = math.atan(math.tan(datos.angle / 2) * proporcion)
        cam.location = centro + direccion * (radio / math.sin(medio) * 1.1)
        cam.rotation_euler = (centro - cam.location).to_track_quat("-Z", "Y").to_euler()
        datos.clip_end = max(1000.0, radio * 20)
        sc.camera = cam
        extra["camara_añadida"] = True
    if not any(o.type == "LIGHT" for o in sc.objects):
        sol = bpy.data.objects.new("LAB_sol", bpy.data.lights.new("LAB_sol", "SUN"))
        sol.rotation_euler = (math.radians(50), 0, math.radians(30))
        sol.data.energy = 3.0
        sc.collection.objects.link(sol)
        extra["luz_añadida"] = True
    return extra


def renderizar(cfg: dict, salida: Path, h: dict) -> dict:
    sc = bpy.context.scene
    r = sc.render
    res = {"motor": cfg.get("motor", "BLENDER_WORKBENCH"), "archivos": []}
    r.engine = res["motor"]
    r.resolution_x, r.resolution_y = cfg.get("resolucion", [640, 360])
    r.resolution_percentage = 100
    res |= encuadrar(sc, h)
    r.use_file_extension = True
    r.use_overwrite = True
    ims = r.image_settings
    t0 = time.monotonic()
    for f in cfg.get("fotogramas", []):
        ims.media_type = "IMAGE"
        ims.file_format = "PNG"
        sc.frame_set(int(f))
        r.filepath = str(salida / f"fotograma_{int(f):04d}")
        bpy.ops.render.render(write_still=True)
        res["archivos"].append(f"fotograma_{int(f):04d}.png")
    if cfg.get("video"):
        fin = min(sc.frame_end, sc.frame_start + int(cfg.get("max_fotogramas_video", 720)) - 1)
        res["video_fotogramas"] = [sc.frame_start, fin]
        final_original = sc.frame_end
        sc.frame_end = fin
        ims.media_type = "VIDEO"
        r.ffmpeg.format = "MPEG4"
        r.ffmpeg.codec = "H264"
        r.ffmpeg.constant_rate_factor = "MEDIUM"
        r.filepath = str(salida / "video.mp4")
        bpy.ops.render.render(animation=True)
        sc.frame_end = final_original
        res["archivos"] += sorted(p.name for p in salida.glob("video*.mp4"))
    res["segundos"] = round(time.monotonic() - t0, 2)
    return res


def principal() -> int:
    cfg = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    salida = Path(cfg["salida"])
    informe = {"fase": "inicio", "blender": bpy.app.version_string, "de_fabrica": bool(bpy.app.factory_startup),
               "scripts_automaticos": bool(bpy.context.preferences.filepaths.use_scripts_auto_execute),
               "con_red": bool(getattr(bpy.app, "online_access", False))}
    ruta = salida / "informe.json"
    escribir(ruta, informe)
    sys.path.insert(0, cfg["lab"])
    import filtro
    if cfg.get("base"):
        bpy.ops.wm.open_mainfile(filepath=cfg["base"], load_ui=False, use_scripts=False)
        informe["escena_de_partida"] = "copia de un .blend"
    elif cfg.get("escena", "vacia") == "vacia":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        informe["escena_de_partida"] = "vacía"
    else:
        informe["escena_de_partida"] = "de fábrica (cubo, cámara y luz)"
    texto = Path(cfg["script"]).read_text(encoding="utf-8")
    motivos = filtro.revisar(texto)
    if hashlib.sha256(texto.encode("utf-8")).hexdigest() != cfg["sha256"]:
        motivos.append("el script no es el que revisó el ejecutor (la huella no coincide)")
    if motivos:
        informe |= {"fase": "rechazado_dentro", "motivos": motivos}
        escribir(ruta, informe)
        return 0
    informe["fase"] = "ejecutando"
    escribir(ruta, informe)
    informe["script"] = ejecutar_script(texto, filtro)
    informe["fase"] = "midiendo"
    escribir(ruta, informe)
    informe["escena"] = hechos(int(cfg.get("muestras", 5)), cfg["limites"])
    escribir(ruta, informe)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(salida / "resultado.blend"), copy=True, compress=True, check_existing=False)
        informe["blend_guardado"] = True
    except RuntimeError as e:
        informe["blend_guardado"] = False
        informe["error_al_guardar"] = str(e)[:300]
    if cfg.get("render") and informe["script"]["ok"] and not informe["escena"]["limites_superados"]:
        informe["fase"] = "renderizando"
        escribir(ruta, informe)
        try:
            informe["render"] = renderizar(cfg["render"], salida, informe["escena"])
        except Exception as e:
            informe["render"] = {"error": f"{type(e).__name__}: {e}"[:500]}
    informe["fase"] = "fin"
    escribir(ruta, informe)
    return 0


if __name__ == "__main__":
    principal()
