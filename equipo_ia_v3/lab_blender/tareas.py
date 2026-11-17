"""Tareas de Blender para los cerebros (laboratorio), de menos a más difícil, con sus comprobaciones medibles.

Cada tarea: `enunciado` (lo único de la tarea que ve el cerebro), `comprobaciones` (para lab_blender/verificador.py; NUNCA
entran en un prompt), `muestras` (fotogramas en los que se mide), `base` (si parte de la copia de un .blend) y `animada`.
`REFERENCIAS` son soluciones escritas por Claude: sirven para comprobar que cada tarea se puede resolver y que el verificador
distingue una solución de otra. Tampoco entran en ningún prompt.
"""

ROBOT_TXT = ("un robot de cajas: «Torso» de 1.0 × 0.6 × 1.2 m con su centro en (0, 0, 2.0); «Cabeza», un cubo de 0.5 m justo "
             "encima del torso, centrada y tocándolo; «Pierna_I» y «Pierna_D» de 0.3 × 0.3 × 1.4 m, debajo del torso, "
             "tocándolo y apoyadas en el suelo (z = 0); «Brazo_I» y «Brazo_D» de 0.25 × 0.25 × 1.0 m, uno a cada lado del "
             "torso y tocándolo. Las piezas «_I» van en x negativa y las «_D» en x positiva, simétricas. Todas las piezas "
             "son hijas de «Torso»")
PIEZAS = ["Torso", "Cabeza", "Pierna_I", "Pierna_D", "Brazo_I", "Brazo_D"]
ROBOT_OK = [
    ("solo", PIEZAS),
    ("dimensiones", "Torso", (1.0, 0.6, 1.2)), ("centro", "Torso", (0, 0, 2.0)),
    ("dimensiones", "Cabeza", (0.5, 0.5, 0.5)), ("encima", "Cabeza", "Torso"), ("toca", "Cabeza", "Torso"),
    ("dimensiones", "Pierna_I", (0.3, 0.3, 1.4)), ("dimensiones", "Pierna_D", (0.3, 0.3, 1.4)),
    ("apoyado", "Pierna_I"), ("apoyado", "Pierna_D"), ("toca", "Pierna_I", "Torso"), ("toca", "Pierna_D", "Torso"),
    ("simetricos", "Pierna_I", "Pierna_D"), ("lado", "Pierna_I", -1),
    ("dimensiones", "Brazo_I", (0.25, 0.25, 1.0)), ("dimensiones", "Brazo_D", (0.25, 0.25, 1.0)),
    ("toca", "Brazo_I", "Torso"), ("toca", "Brazo_D", "Torso"), ("simetricos", "Brazo_I", "Brazo_D"), ("lado", "Brazo_I", -1),
    *[("desciende", p, "Torso") for p in PIEZAS[1:]],
    # tanda 12 (2026-11-15): «toca» aceptaba brazos metidos en el torso o colgando bajo él, dentro de las piernas
    ("a_un_lado", "Brazo_I", "Torso", -1), ("a_un_lado", "Brazo_D", "Torso", 1), ("sin_solapes", PIEZAS),
]
BASE_ROBOT_TXT = ("La escena ya contiene un robot hecho con seis cajas llamadas «Torso», «Cabeza», «Pierna_I», «Pierna_D», "
                  "«Brazo_I» y «Brazo_D» (la cabeza es un cubo de 0.5 m cuya cara de arriba está a z = 3.1, centrada en "
                  "x = 0, y = 0). No crees el robot otra vez ni borres nada. ")

TAREAS = {
    "T01": {"enunciado": "Crea un cubo llamado «Caja» de 2 m de lado, apoyado en el suelo, con su centro en (0, 0, 1).",
            "comprobaciones": [("solo", ["Caja"]), ("dimensiones", "Caja", (2, 2, 2)), ("centro", "Caja", (0, 0, 1)),
                               ("apoyado", "Caja")]},
    "T02": {"enunciado": "Crea cinco cubos de 1 m de lado llamados «Cubo_1» a «Cubo_5», en fila a lo largo del eje X, "
                         "separados 2 m entre centros: el centro de «Cubo_1» en (0, 0, 0.5) y el de «Cubo_5» en (8, 0, 0.5).",
            "comprobaciones": [("solo", [f"Cubo_{i}" for i in range(1, 6)]),
                               *[("centro", f"Cubo_{i}", (2 * (i - 1), 0, 0.5)) for i in range(1, 6)],
                               *[("dimensiones", f"Cubo_{i}", (1, 1, 1)) for i in range(1, 6)]]},
    "T03": {"enunciado": "Crea una esfera llamada «Bola» de 1 m de radio con su centro en (0, 0, 1) y ponle un material "
                         "llamado «Rojo» que en el render se vea rojo puro (1, 0, 0).",
            "comprobaciones": [("solo", ["Bola"]), ("dimensiones", "Bola", (2, 2, 2), 0.1), ("centro", "Bola", (0, 0, 1)),
                               ("color", "Bola", (1, 0, 0))]},
    "T04": {"enunciado": "Crea una caja «Torso» de 1.0 × 0.6 × 1.2 m con su centro en (0, 0, 2.0) y un cubo «Cabeza» de 0.5 m "
                         "de lado justo encima del torso, centrado y tocándolo. «Cabeza» tiene que ser hija de «Torso».",
            "comprobaciones": [("solo", ["Torso", "Cabeza"]), ("dimensiones", "Torso", (1.0, 0.6, 1.2)),
                               ("centro", "Torso", (0, 0, 2.0)), ("dimensiones", "Cabeza", (0.5, 0.5, 0.5)),
                               ("centro", "Cabeza", (0, 0, 2.85)), ("toca", "Cabeza", "Torso"), ("encima", "Cabeza", "Torso"),
                               ("desciende", "Cabeza", "Torso")]},
    "T05": {"enunciado": f"Crea {ROBOT_TXT}.", "comprobaciones": ROBOT_OK},
    "T06": {"enunciado": "Crea un cubo «Movil» de 1 m de lado y anímalo: en el fotograma 1 su centro está en (0, 0, 0.5) y en "
                         "el fotograma 48 en (5, 0, 0.5). La escena va del fotograma 1 al 48 a 24 fps.",
            "animada": True,
            "comprobaciones": [("solo", ["Movil"]), ("fotogramas", 1, 48, 24), ("dimensiones", "Movil", (1, 1, 1)),
                               ("centro", "Movil", (0, 0, 0.5)), ("desplazamiento", "Movil", (5, 0, 0)), ("apoyado", "Movil")]},
    "T07": {"enunciado": "Crea un cilindro «Torreta» de 0.5 m de radio y 1 m de alto, de pie, con su centro en (0, 0, 0.5). "
                         "Anímalo para que gire 90 grados alrededor del eje Z entre el fotograma 1 y el 24, sin moverse "
                         "del sitio. La escena va del fotograma 1 al 24.",
            "animada": True,
            "comprobaciones": [("solo", ["Torreta"]), ("fotogramas", 1, 24), ("dimensiones", "Torreta", (1, 1, 1), 0.06),
                               ("centro", "Torreta", (0, 0, 0.5)), ("giro", "Torreta", 2, 90.0),
                               ("desplazamiento", "Torreta", (0, 0, 0))]},
    "T08": {"enunciado": f"Crea {ROBOT_TXT}. Después anima el robot entero para que avance 4 m hacia Y negativa entre el "
                         "fotograma 1 y el 48 (sin subir ni bajar, con todas las piezas juntas). La escena va del 1 al 48.",
            "animada": True,
            "comprobaciones": [*ROBOT_OK, ("fotogramas", 1, 48),
                               *[("desplazamiento", p, (0, -4, 0)) for p in PIEZAS]]},
    "T09": {"enunciado": "Crea un esqueleto (objeto de tipo armature) llamado «Rig» con tres huesos llamados «Torso», "
                         "«Pierna_I» y «Pierna_D».",
            "comprobaciones": [("existe", "Rig", "ARMATURE"), ("huesos", "Rig", ["Torso", "Pierna_I", "Pierna_D"])]},
    "T10": {"enunciado": "Crea una caja «Cuerpo» de 0.8 × 0.5 × 1.0 m con su centro en (0, 0, 0.9) y dos pies, «Pie_I» y "
                         "«Pie_D», de 0.25 × 0.5 × 0.2 m apoyados en el suelo, con centros en (-0.25, 0, 0.1) y (0.25, 0, 0.1), "
                         "hijos de «Cuerpo». Anima una caminata del fotograma 1 al 48: el cuerpo avanza 3 m hacia Y positiva; "
                         "los pies avanzan con él y se levantan por turnos: primero «Pie_I» sube al menos 0.2 m y vuelve al "
                         "suelo, y después «Pie_D» hace lo mismo. Nunca están los dos en el aire a la vez y ninguno baja de z = 0.",
            "animada": True, "muestras": 13,
            "comprobaciones": [("solo", ["Cuerpo", "Pie_I", "Pie_D"]), ("fotogramas", 1, 48),
                               ("dimensiones", "Cuerpo", (0.8, 0.5, 1.0)), ("dimensiones", "Pie_I", (0.25, 0.5, 0.2)),
                               ("dimensiones", "Pie_D", (0.25, 0.5, 0.2)), ("lado", "Pie_I", -1), ("lado", "Pie_D", 1),
                               ("desciende", "Pie_I", "Cuerpo"), ("desciende", "Pie_D", "Cuerpo"),
                               ("desplazamiento", "Cuerpo", (0, 3, 0)), ("desplazamiento", "Pie_I", (0, 3, 0)),
                               ("desplazamiento", "Pie_D", (0, 3, 0)), ("alternan", "Pie_I", "Pie_D", 0.2),
                               ("no_se_hunde", ["Cuerpo", "Pie_I", "Pie_D"])]},
    "B01": {"enunciado": BASE_ROBOT_TXT + "Ponle a «Cabeza» un material llamado «Azul» que en el render se vea azul puro "
                                          "(0, 0, 1). No cambies nada más.",
            "base": "robot", "comprobaciones": [*ROBOT_OK, ("color", "Cabeza", (0, 0, 1))]},
    "B02": {"enunciado": BASE_ROBOT_TXT + "Añade un cilindro «Antena» de 0.05 m de radio y 0.6 m de alto, de pie, centrado "
                                          "encima de la cabeza y tocándola, hijo de «Cabeza».",
            "base": "robot",
            "comprobaciones": [("solo", PIEZAS + ["Antena"]), *ROBOT_OK[1:], ("dimensiones", "Antena", (0.1, 0.1, 0.6)),
                               ("centro", "Antena", (0, 0, 3.4)), ("toca", "Antena", "Cabeza"), ("encima", "Antena", "Cabeza"),
                               ("desciende", "Antena", "Cabeza")]},
}
BASES = {"robot": "T05"}                                     # el .blend de partida es el resultado de esta referencia

# --- soluciones de referencia (escritas por Claude; no entran en ningún prompt) ---------------------------------------------
_CAJA = '''import bpy
from math import radians

def caja(nombre, tam, pos, padre=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    ob = bpy.context.active_object
    ob.name = nombre
    ob.scale = tam
    if padre:
        ob.parent = padre
        ob.matrix_parent_inverse = padre.matrix_world.inverted()
    return ob

def color(ob, nombre, rgb):
    m = bpy.data.materials.new(nombre)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    ob.data.materials.clear()
    ob.data.materials.append(m)
'''
_ROBOT = _CAJA + '''
torso = caja("Torso", (1.0, 0.6, 1.2), (0, 0, 2.0))
bpy.context.view_layer.update()
caja("Cabeza", (0.5, 0.5, 0.5), (0, 0, 2.85), torso)
caja("Pierna_I", (0.3, 0.3, 1.4), (-0.3, 0, 0.7), torso)
caja("Pierna_D", (0.3, 0.3, 1.4), (0.3, 0, 0.7), torso)
caja("Brazo_I", (0.25, 0.25, 1.0), (-0.625, 0, 2.1), torso)
caja("Brazo_D", (0.25, 0.25, 1.0), (0.625, 0, 2.1), torso)
'''
REFERENCIAS = {
    "T01": _CAJA + 'caja("Caja", (2, 2, 2), (0, 0, 1))\n',
    "T02": _CAJA + 'for i in range(5):\n    caja(f"Cubo_{i + 1}", (1, 1, 1), (2 * i, 0, 0.5))\n',
    "T03": _CAJA + 'bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 1))\nb = bpy.context.active_object\n'
                   'b.name = "Bola"\ncolor(b, "Rojo", (1, 0, 0))\n',
    "T04": _CAJA + 't = caja("Torso", (1.0, 0.6, 1.2), (0, 0, 2.0))\nbpy.context.view_layer.update()\n'
                   'caja("Cabeza", (0.5, 0.5, 0.5), (0, 0, 2.85), t)\n',
    "T05": _ROBOT,
    "T06": _CAJA + 'm = caja("Movil", (1, 1, 1), (0, 0, 0.5))\nsc = bpy.context.scene\nsc.frame_start, sc.frame_end = 1, 48\n'
                   'sc.render.fps = 24\nm.keyframe_insert(data_path="location", frame=1)\nm.location.x = 5\n'
                   'm.keyframe_insert(data_path="location", frame=48)\n',
    "T07": _CAJA + 'bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1, location=(0, 0, 0.5))\n'
                   't = bpy.context.active_object\nt.name = "Torreta"\nsc = bpy.context.scene\n'
                   'sc.frame_start, sc.frame_end = 1, 24\nt.keyframe_insert(data_path="rotation_euler", frame=1)\n'
                   't.rotation_euler.z = radians(90)\nt.keyframe_insert(data_path="rotation_euler", frame=24)\n',
    "T08": _ROBOT + 'sc = bpy.context.scene\nsc.frame_start, sc.frame_end = 1, 48\n'
                    'torso.keyframe_insert(data_path="location", frame=1)\ntorso.location.y = -4\n'
                    'torso.keyframe_insert(data_path="location", frame=48)\n',
    "T09": 'import bpy\narm = bpy.data.armatures.new("Rig")\nrig = bpy.data.objects.new("Rig", arm)\n'
           'bpy.context.scene.collection.objects.link(rig)\nbpy.context.view_layer.objects.active = rig\n'
           'bpy.ops.object.mode_set(mode="EDIT")\n'
           'for nombre, cabeza, cola in (("Torso", (0, 0, 1.4), (0, 0, 2.6)), ("Pierna_I", (-0.3, 0, 1.4), (-0.3, 0, 0)),\n'
           '                             ("Pierna_D", (0.3, 0, 1.4), (0.3, 0, 0))):\n'
           '    h = arm.edit_bones.new(nombre)\n    h.head, h.tail = cabeza, cola\n'
           'bpy.ops.object.mode_set(mode="OBJECT")\n',
    "T10": _CAJA + 'c = caja("Cuerpo", (0.8, 0.5, 1.0), (0, 0, 0.9))\nbpy.context.view_layer.update()\n'
                   'pi_ = caja("Pie_I", (0.25, 0.5, 0.2), (-0.25, 0, 0.1), c)\npd = caja("Pie_D", (0.25, 0.5, 0.2), (0.25, 0, 0.1), c)\n'
                   'sc = bpy.context.scene\nsc.frame_start, sc.frame_end = 1, 48\n'
                   'c.keyframe_insert(data_path="location", frame=1)\nc.location.y = 3\n'
                   'c.keyframe_insert(data_path="location", frame=48)\n'
                   'for pie, cuadros in ((pi_, (1, 12, 24, 48)), (pd, (1, 24, 36, 48))):\n'
                   '    z0 = pie.location.z\n'
                   '    alturas = (z0, z0 + 0.3, z0, z0) if pie is pi_ else (z0, z0, z0 + 0.3, z0)\n'
                   '    for f, z in zip(cuadros, alturas):\n        pie.location.z = z\n'
                   '        pie.keyframe_insert(data_path="location", index=2, frame=f)\n',
    "B01": _CAJA + 'color(bpy.data.objects["Cabeza"], "Azul", (0, 0, 1))\n',
    "B02": _CAJA + 'bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.6, location=(0, 0, 3.4))\n'
                   'a = bpy.context.active_object\na.name = "Antena"\ncab = bpy.data.objects["Cabeza"]\n'
                   'a.parent = cab\na.matrix_parent_inverse = cab.matrix_world.inverted()\n',
}
