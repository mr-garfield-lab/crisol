"""Banco de revisión de código · corpus DETERMINISTA con errores plantados y su línea exacta (oráculo).

Código original escrito para el banco (no copiado de ningún proyecto). Dos programas por lenguaje; a cada uno se le
aplican: cinco errores de una sola clase cada uno, dos versiones correctas (la segunda con algo que PARECE un error y no
lo es) y un archivo con dos errores de fases distintas (uno de sintaxis que tapa otro de nombres).

Un defecto es (clase, buscar, reemplazar, marcas): `buscar` aparece exactamente una vez en la base, y la línea del
oráculo es la de cada `marca` en el archivo YA modificado (si se borra un import, las líneas se desplazan).
Fuera de este banco, por decisión del usuario (2026-11-15): código malicioso y errores de lógica (necesitan ejecutar).
"""
from __future__ import annotations

PY_INVENTARIO = '''"""Inventario de un almacén."""
import json

LIMITE_STOCK = 500


def cargar(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def total_unidades(inventario):
    total = 0
    for articulo in inventario:
        total += articulo["unidades"]
    return total


def reponer(articulo, cantidad):
    nuevo = articulo["unidades"] + cantidad
    if nuevo > LIMITE_STOCK:
        nuevo = LIMITE_STOCK
    articulo["unidades"] = nuevo
    return articulo


def por_categoria(inventario, categoria):
    return [a for a in inventario if a["categoria"] == categoria]


def informe(inventario):
    lineas = []
    for categoria in sorted({a["categoria"] for a in inventario}):
        grupo = por_categoria(inventario, categoria)
        lineas.append(f"{categoria}: {total_unidades(grupo)}")
    return "\\n".join(lineas)
'''

PY_RUTAS = '''"""Cálculo de rutas de reparto."""
from datetime import timedelta

VELOCIDAD_MEDIA = 40


def duracion(distancia_km):
    horas = distancia_km / VELOCIDAD_MEDIA
    return timedelta(hours=horas)


def ordenar_paradas(paradas):
    return sorted(paradas, key=lambda p: p["distancia"])


def distancia_total(paradas):
    suma = 0
    for parada in paradas:
        suma += parada["distancia"]
    return suma


def plan(paradas, salida):
    ordenadas = ordenar_paradas(paradas)
    llegada = salida + duracion(distancia_total(ordenadas))
    return {"paradas": ordenadas, "llegada": llegada}


def resumen(paradas, salida):
    datos = plan(paradas, salida)
    return f"{len(datos['paradas'])} paradas, llegada {datos['llegada']}"
'''

JAVA_INVENTARIO = '''import java.util.ArrayList;
import java.util.List;

public class Inventario {
    static final int LIMITE_STOCK = 500;
    private final List<Integer> unidades = new ArrayList<>();

    public void agregar(int cantidad) {
        unidades.add(Math.min(cantidad, LIMITE_STOCK));
    }

    public int total() {
        int suma = 0;
        for (int u : unidades) {
            suma += u;
        }
        return suma;
    }

    public double media() {
        if (unidades.isEmpty()) {
            return 0.0;
        }
        return (double) total() / unidades.size();
    }

    public String informe(String titulo) {
        return titulo + ": " + total() + " unidades, media " + media();
    }

    public static void main(String[] args) {
        Inventario inv = new Inventario();
        inv.agregar(10);
        inv.agregar(700);
        System.out.println(inv.informe("Almacen"));
    }
}
'''

JAVA_RUTAS = '''import java.util.Arrays;

public class Rutas {
    static final double VELOCIDAD_MEDIA = 40.0;

    static double horas(double distanciaKm) {
        return distanciaKm / VELOCIDAD_MEDIA;
    }

    static double distanciaTotal(double[] tramos) {
        double suma = 0;
        for (double t : tramos) {
            suma += t;
        }
        return suma;
    }

    static double[] ordenar(double[] tramos) {
        double[] copia = Arrays.copyOf(tramos, tramos.length);
        Arrays.sort(copia);
        return copia;
    }

    static String resumen(double[] tramos) {
        double total = distanciaTotal(tramos);
        return tramos.length + " tramos, " + total + " km, " + horas(total) + " h";
    }

    public static void main(String[] args) {
        double[] tramos = {12.5, 3.0, 40.0};
        System.out.println(resumen(ordenar(tramos)));
    }
}
'''

# (clase, buscar, reemplazar, marcas de la línea del error en el archivo modificado)
DEFECTOS = {
    ("python", "inventario"): [
        ("sintaxis", "def reponer(articulo, cantidad):", "def reponer(articulo, cantidad)", ["def reponer("]),
        ("nombre", "    return total\n", "    return totl\n", ["return totl"]),
        ("import", "        nuevo = LIMITE_STOCK\n", "        nuevo = math.floor(LIMITE_STOCK)\n", ["math.floor"]),
        ("argumentos", "grupo = por_categoria(inventario, categoria)", "grupo = por_categoria(inventario)",
         ["grupo = por_categoria(inventario)"]),
        ("nombre", "    return [a for a in inventario if a[\"categoria\"] == categoria]",
         "    return [a for a in inventarios if a[\"categoria\"] == categoria]", ["in inventarios"]),
    ],
    ("python", "rutas"): [
        ("sintaxis", "    for parada in paradas:", "    for parada in paradas", ["for parada in paradas"]),
        ("nombre", "    return suma\n", "    return suma_total\n", ["return suma_total"]),
        ("import", "    horas = distancia_km / VELOCIDAD_MEDIA",
         "    horas = math.ceil(distancia_km / VELOCIDAD_MEDIA)", ["math.ceil"]),
        ("argumentos", "duracion(distancia_total(ordenadas))", "duracion(distancia_total(ordenadas), salida)",
         ["duracion(distancia_total(ordenadas), salida)"]),
        ("argumentos", "    datos = plan(paradas, salida)", "    datos = plan(paradas)", ["datos = plan(paradas)"]),
    ],
    ("java", "Inventario"): [
        ("sintaxis", "            suma += u;", "            suma += u", ["suma += u"]),
        ("simbolo", "        return suma;", "        return sumaTotal;", ["return sumaTotal"]),
        ("tipos", "        int suma = 0;", "        int suma = \"0\";", ["int suma = \"0\""]),
        ("import", "import java.util.ArrayList;\n", "", ["new ArrayList<>()"]),
        ("argumentos", "        inv.agregar(10);", "        inv.agregar(10, 5);", ["inv.agregar(10, 5)"]),
    ],
    ("java", "Rutas"): [
        ("sintaxis", "        Arrays.sort(copia);", "        Arrays.sort(copia)", ["Arrays.sort(copia)"]),
        ("simbolo", "        return suma;", "        return sumaKm;", ["return sumaKm"]),
        ("tipos", "        double total = distanciaTotal(tramos);", "        int total = distanciaTotal(tramos);",
         ["int total = distanciaTotal"]),
        ("import", "import java.util.Arrays;\n", "", ["Arrays.copyOf", "Arrays.sort"]),
        ("argumentos", "horas(total)", "horas(total, 2)", ["horas(total, 2)"]),
    ],
}

# Versión correcta que PARECE sospechosa: se añade antes de la última línea útil del programa.
LIMPIOS_TRAMPA = {
    ("python", "inventario"): ('''

def ajustado(x):
    return x * FACTOR


FACTOR = 2
''', "constante usada en una función y definida más abajo (válido en Python)"),
    ("python", "rutas"): ('''

def contador():
    n = 0

    def siguiente():
        nonlocal n
        n += 1
        return n
    return siguiente
''', "variable de la función exterior modificada con nonlocal (válido)"),
    ("java", "Inventario"): ('''
    public int sumaVarios(int... valores) {
        int s = 0;
        for (int v : valores) {
            s += v;
        }
        return s;
    }
''', "método con varargs (int...) llamado con cualquier número de argumentos (válido)"),
    ("java", "Rutas"): ('''
    static String nivel(double km) {
        var etiqueta = km > 30 ? "largo" : "corto";
        return etiqueta;
    }
''', "inferencia de tipo con var y operador ternario (válido)"),
}

# Dos fases: (sintaxis, que tapa) + (nombre/símbolo, que solo aparece al arreglar la primera)
DOS_FASES = {
    ("python", "inventario"): [("sintaxis", "def reponer(articulo, cantidad):", "def reponer(articulo, cantidad)",
                                ["def reponer("]),
                               ("nombre", "    return total\n", "    return totl\n", ["return totl"])],
    ("python", "rutas"): [("sintaxis", "    for parada in paradas:", "    for parada in paradas",
                           ["for parada in paradas"]),
                          ("nombre", "    datos = plan(paradas, salida)", "    datos = plan(parada, salida)",
                           ["datos = plan(parada, salida)"])],
    ("java", "Inventario"): [("sintaxis", "            suma += u;", "            suma += u", ["suma += u"]),
                             ("simbolo", "        return titulo + ", "        return tituloX + ", ["return tituloX"])],
    ("java", "Rutas"): [("sintaxis", "        Arrays.sort(copia);", "        Arrays.sort(copia)",
                         ["Arrays.sort(copia)"]),
                        ("simbolo", "        return suma;", "        return sumaKm;", ["return sumaKm"])],
}

BASES = {("python", "inventario"): PY_INVENTARIO, ("python", "rutas"): PY_RUTAS,
         ("java", "Inventario"): JAVA_INVENTARIO, ("java", "Rutas"): JAVA_RUTAS}


def _lineas_de(texto: str, marcas: list) -> list:
    out = []
    for m in marcas:
        hits = [i for i, l in enumerate(texto.splitlines(), 1) if m in l]
        if len(hits) != 1:
            raise ValueError(f"la marca {m!r} aparece {len(hits)} veces")
        out.append(hits[0])
    return sorted(set(out))


def _aplicar(texto: str, buscar: str, reemplazar: str) -> str:
    if texto.count(buscar) != 1:
        raise ValueError(f"{buscar!r} aparece {texto.count(buscar)} veces")
    return texto.replace(buscar, reemplazar)


def _trampa(base: str, lang: str, extra: str) -> str:
    if lang == "python":
        return base.rstrip("\n") + "\n" + extra
    i = base.rstrip().rfind("}")                       # antes de la llave que cierra la clase
    return base[:i].rstrip("\n") + "\n" + extra + base[i:]


def generar() -> list:
    """Lista de casos: {id, lenguaje, archivo, codigo, errores: [{linea, clase}], fases: [[linea…], …], nota}."""
    casos = []
    for (lang, nombre), base in BASES.items():
        archivo = f"{nombre}.py" if lang == "python" else f"{nombre}.java"
        pre = f"{'PY' if lang == 'python' else 'JV'}_{nombre[:3].upper()}"
        for i, (clase, buscar, reemplazar, marcas) in enumerate(DEFECTOS[(lang, nombre)], 1):
            codigo = _aplicar(base, buscar, reemplazar)
            lineas = _lineas_de(codigo, marcas)
            casos.append({"id": f"{pre}_E{i}", "lenguaje": lang, "archivo": archivo, "codigo": codigo,
                          "errores": [{"linea": n, "clase": clase} for n in lineas], "fases": [lineas],
                          "nota": f"un error de {clase}"})
        casos.append({"id": f"{pre}_OK1", "lenguaje": lang, "archivo": archivo, "codigo": base, "errores": [],
                      "fases": [], "nota": "correcto"})
        extra, nota = LIMPIOS_TRAMPA[(lang, nombre)]
        casos.append({"id": f"{pre}_OK2", "lenguaje": lang, "archivo": archivo, "codigo": _trampa(base, lang, extra),
                      "errores": [], "fases": [], "nota": f"correcto que parece sospechoso: {nota}"})
        codigo = base
        for _, buscar, reemplazar, _ in DOS_FASES[(lang, nombre)]:
            codigo = _aplicar(codigo, buscar, reemplazar)
        fases = [_lineas_de(codigo, m) for _, _, _, m in DOS_FASES[(lang, nombre)]]
        casos.append({"id": f"{pre}_F2", "lenguaje": lang, "archivo": archivo, "codigo": codigo,
                      "errores": [{"linea": n, "clase": c} for (c, _, _, _), f in zip(DOS_FASES[(lang, nombre)], fases)
                                  for n in f],
                      "fases": fases, "nota": "dos fases: la sintaxis tapa un error de nombres"})
    return casos
