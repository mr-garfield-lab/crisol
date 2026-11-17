"""V2-E.5-r2: sondeo de importaciones gráficas en un proceso aislado (lo lanza test_v2e5r2).

Uso: python3 -B -I _sondeo_importaciones.py <dir_src> [--precargar MOD]... [--ruta-extra DIR]

1. (Opcional) añade DIR al principio de sys.path e importa los módulos de --precargar, simulando un
   entorno que ya los tenía cargados (p. ej. Pillow importado por un sitecustomize).
2. Toma una FOTO de sys.modules (línea base).
3. Importa el paquete eq2 de <dir_src> y todos sus módulos.
4. Imprime JSON: los módulos gráficos ya presentes antes (precargados) y los que aparecieron
   DESPUÉS de importar eq2 (los únicos atribuibles a Equipo IA).
No escribe archivos.
"""
import importlib
import json
import pkgutil
import sys

GRAFICOS = ("tkinter", "_tkinter", "turtle", "pygame", "PIL", "PyQt5", "PyQt6", "PySide2", "PySide6",
            "kivy", "wx", "cv2", "matplotlib", "gi")


def es_grafico(nombre: str) -> bool:
    return nombre.split(".")[0] in GRAFICOS


def main(argv):
    src, resto = argv[0], argv[1:]
    precargar, extra = [], None
    while resto:
        op, val, resto = resto[0], resto[1], resto[2:]
        if op == "--precargar":
            precargar.append(val)
        elif op == "--ruta-extra":
            extra = val
        else:
            raise SystemExit(f"opción desconocida: {op}")
    if extra:
        sys.path.insert(0, extra)
    for m in precargar:
        importlib.import_module(m)
    base = set(sys.modules)
    sys.path.insert(0, src)
    import eq2
    errores = []
    for m in sorted(pkgutil.iter_modules(eq2.__path__), key=lambda x: x.name):
        try:
            importlib.import_module("eq2." + m.name)
        except ImportError as e:            # se informa: una importación que falla no se oculta
            errores.append(f"eq2.{m.name}: {e}")
    despues = set(sys.modules)
    print(json.dumps({"precargados": sorted(k for k in base if es_grafico(k)),
                      "nuevos": sorted(k for k in despues - base if es_grafico(k)),
                      "modulos_eq2": sorted(k for k in despues if k == "eq2" or k.startswith("eq2.")),
                      "errores": errores}))


if __name__ == "__main__":
    main(sys.argv[1:])
