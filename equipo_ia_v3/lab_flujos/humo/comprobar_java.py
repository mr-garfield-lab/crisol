"""Comprobación de la lectura de Java de Contexto Ligero, con un mod de ejemplo ORIGINAL (estilo Forge/Fabric).

    python -B -X utf8 lab_flujos/humo/comprobar_java.py          (desde equipo_ia_v3/; sin GPU ni red)

El mod se escribe en una carpeta temporal y contiene a propósito lo difícil: eventos con anotaciones, un mixin con
`@Inject` en varias líneas, enums con constructor y valores, interfaz con método por defecto y abstracto, `record`,
genéricos, sobrecargas, `import static`, lambdas, clase anónima, bloque `static`, inicializadores de array, varias
variables en una línea y llaves dentro de caracteres, textos y bloques de texto. Sale con 0 solo si todo pasa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CL = AQUI.parents[2] / "fuentes" / "contexto_ligero_v35" / "contexto_v3.py"
RESULTADOS = []

MOD = {
    "src/main/java/es/ejemplo/volcanes/Volcanes.java": '''package es.ejemplo.volcanes;

import es.ejemplo.volcanes.util.Calor;
import static es.ejemplo.volcanes.util.Calor.limitar;
import java.util.*;

@Mod("volcanes")
public class Volcanes {
    public static final String ID_MOD = "volcanes";
    static final int[] NIVELES_LAVA = {1, 2, 4, 8};
    private static int erupciones, avisos;
    private final Map<String, List<Integer>> registro = new HashMap<>();

    static {
        System.out.println("cargando { volcanes }");
    }

    public Volcanes() {
        registrarEventos();
    }

    private void registrarEventos() {
        Runnable r = new Runnable() {
            @Override
            public void run() { erupciones++; }
        };
        List.of(1, 2).forEach(x -> { avisos += x; });
    }

    @SubscribeEvent
    public void alRomperBloque(EventoRomper evento) {
        char llave = '{';
        if (evento.bloque().esVolcanico()) {
            int calor = Calor.calcularCalor(evento.profundidad());
            evento.jugador().quemar(limitar(calor));
        }
    }

    public int potencia(int nivel) { return nivel * 2; }
    public int potencia(int nivel, double factor) { return (int) (nivel * factor); }

    public static <T extends Comparable<T>> T mayor(List<T> lista) {
        return Collections.max(lista);
    }
}
''',
    "src/main/java/es/ejemplo/volcanes/util/Calor.java": '''package es.ejemplo.volcanes.util;

public final class Calor {
    public static final int CALOR_MAXIMO = 1200;
    private static final String NOTA = """
        bloque de texto con { llaves } y "comillas"
        """;

    public static int calcularCalor(int profundidad) {
        return limitar(profundidad * 15);
    }

    public static int limitar(int valor) {
        return Math.min(valor, CALOR_MAXIMO);
    }
}
''',
    "src/main/java/es/ejemplo/volcanes/Roca.java": '''package es.ejemplo.volcanes;

public enum Roca {
    BASALTO(3, true), OBSIDIANA(9, false) {
        @Override
        public boolean fundible() { return false; }
    }, PIEDRA_POMEZ(1, true);

    public static final int DUREZA_MAXIMA = 10;
    private final int dureza;
    private final boolean flota;

    Roca(int dureza, boolean flota) {
        this.dureza = dureza;
        this.flota = flota;
    }

    public boolean fundible() { return dureza < DUREZA_MAXIMA; }
}
''',
    "src/main/java/es/ejemplo/volcanes/Calentable.java": '''package es.ejemplo.volcanes;

public interface Calentable {
    int TEMPERATURA_BASE = 20;

    int temperatura();

    default boolean quema() {
        return temperatura() > TEMPERATURA_BASE * 3;
    }
}

record Erupcion(int fuerza, String volcan) {
    Erupcion {
        if (fuerza < 0) throw new IllegalArgumentException("fuerza { negativa }");
    }
}
''',
    "src/main/java/es/ejemplo/volcanes/mixin/MixinJugador.java": '''package es.ejemplo.volcanes.mixin;

@Mixin(Jugador.class)
public abstract class MixinJugador {
    @Inject(
        method = "tick",
        at = @At("HEAD")
    )
    private void alTick(CallbackInfo ci) {
        // { comentario con llaves }
    }
}
''',
}

ESPERADOS = {  # nombre del símbolo -> (tipo, línea inicial, línea final) en su archivo
    "Volcanes.java": {"Volcanes": ("ClassDef", 7, 45), "Volcanes.ID_MOD": ("Assign", 9, 9),
                      "Volcanes.NIVELES_LAVA": ("Assign", 10, 10), "Volcanes.erupciones": ("Assign", 11, 11),
                      "Volcanes.avisos": ("Assign", 11, 11), "Volcanes.registro": ("Assign", 12, 12),
                      "Volcanes.Volcanes": ("FunctionDef", 18, 20), "Volcanes.registrarEventos": ("FunctionDef", 22, 28),
                      "Volcanes.alRomperBloque": ("FunctionDef", 30, 37), "Volcanes.potencia": ("FunctionDef", 39, 39),
                      "Volcanes.potencia#2": ("FunctionDef", 40, 40), "Volcanes.mayor": ("FunctionDef", 42, 44)},
    "Calor.java": {"Calor": ("ClassDef", 3, 16), "Calor.CALOR_MAXIMO": ("Assign", 4, 4), "Calor.NOTA": ("Assign", 5, 7),
                   "Calor.calcularCalor": ("FunctionDef", 9, 11), "Calor.limitar": ("FunctionDef", 13, 15)},
    "Roca.java": {"Roca": ("ClassDef", 3, 19), "Roca.BASALTO": ("Assign", 4, 7), "Roca.OBSIDIANA": ("Assign", 4, 7),
                  "Roca.PIEDRA_POMEZ": ("Assign", 4, 7), "Roca.DUREZA_MAXIMA": ("Assign", 9, 9),
                  "Roca.dureza": ("Assign", 10, 10), "Roca.Roca": ("FunctionDef", 13, 16),
                  "Roca.fundible": ("FunctionDef", 18, 18), "Roca.OBSIDIANA.fundible": ("FunctionDef", 5, 6)},
    "Calentable.java": {"Calentable": ("ClassDef", 3, 11), "Calentable.TEMPERATURA_BASE": ("Assign", 4, 4),
                        "Calentable.temperatura": ("FunctionDef", 6, 6), "Calentable.quema": ("FunctionDef", 8, 10),
                        "Erupcion": ("ClassDef", 13, 17)},
    "MixinJugador.java": {"MixinJugador": ("ClassDef", 3, 12), "MixinJugador.alTick": ("FunctionDef", 5, 11)},
}


def comprobar(nombre: str, ok: bool, detalle: str = "") -> None:
    RESULTADOS.append(ok)
    print(f"[{'PASA' if ok else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def cl(db: Path, *args) -> dict:
    r = subprocess.run([sys.executable, "-B", "-X", "utf8", str(CL), "--db", str(db), *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout)


def main() -> int:
    sys.path.insert(0, str(CL.parent))
    from contexto_core.index import _java_metadata
    base = Path(tempfile.mkdtemp(prefix="java_mod_"))
    try:
        raiz = base / "mod"
        for rel, codigo in MOD.items():
            (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
            (raiz / rel).write_text(codigo, encoding="utf-8", newline="\n")
        # 1) símbolos, tipos y líneas exactas
        for rel in MOD:
            f = raiz / rel
            syms = {s["name"]: s for s in _java_metadata(f.read_bytes())[0]}
            for nombre, (tipo, ini, fin) in ESPERADOS[f.name].items():
                s = syms.get(nombre)
                ok = bool(s) and (s["kind"], s["line"], s["end"]) == (tipo, ini, fin)
                comprobar(f"{f.name}: {nombre}", ok, "" if ok else f"esperado {tipo} L{ini}-L{fin}, obtenido "
                          + (f"{s['kind']} L{s['line']}-L{s['end']}" if s else "nada"))
        v = {s["name"]: s for s in _java_metadata((raiz / list(MOD)[0]).read_bytes())[0]}
        comprobar("la clase anónima no se toma por un método", "Volcanes.Runnable" not in v)
        comprobar("anotación @SubscribeEvent buscable", "SubscribeEvent" in v["Volcanes.alRomperBloque"]["refs"])
        m = {s["name"]: s for s in _java_metadata((raiz / list(MOD)[4]).read_bytes())[0]}
        comprobar("anotación @Inject en varias líneas incluida", "Inject" in m["MixinJugador.alTick"]["refs"])
        comprobar("llamadas con receptor", "Calor.calcularCalor" in v["Volcanes.alRomperBloque"]["calls"])
        # 2) índice, búsqueda en lenguaje normal y llamadas entre archivos
        db = base / "indice.sqlite3"
        s = cl(db, "scan", str(raiz))
        comprobar("indexa los 5 archivos Java", s["indexed_total"] == 5 and s["skipped"] == 0, json.dumps(
            {k: s[k] for k in ("indexed_total", "skipped", "symbol_count", "edge_count")}))
        import sqlite3
        aristas = set(sqlite3.connect(db).execute("SELECT src_symbol,dst_symbol,kind FROM code_edges"))
        for a in [("Volcanes.alRomperBloque", "Calor.calcularCalor", "import_call"),
                  ("Volcanes.alRomperBloque", "Calor.limitar", "import_call"),
                  ("Calor.calcularCalor", "Calor.limitar", "local_call"),
                  ("Volcanes.Volcanes", "Volcanes.registrarEventos", "local_call")]:
            comprobar(f"llamada {a[0]} → {a[1]} ({a[2]})", a in aristas)
        for pregunta, esperado in [("qué pasa al romper un bloque volcánico", "Volcanes.alRomperBloque"),
                                   ("calor máximo", "Calor.CALOR_MAXIMO"),
                                   ("dureza máxima de la roca", "Roca.DUREZA_MAXIMA"),
                                   ("mixin del tick del jugador", "MixinJugador.alTick")]:
            r = cl(db, "query", pregunta)
            nombres = [x["name"] for res in (r if isinstance(r, list) else r["results"])[:3] for x in res["symbols"]]
            comprobar(f"búsqueda «{pregunta}»", esperado in nombres, f"primeros: {nombres[:4]}")
        # 3) bundle: el método, su contexto de clase y lo que llama en otro archivo
        b = cl(db, "bundle", str(raiz), "romper bloque volcánico calor", "--require",
               "src/main/java/es/ejemplo/volcanes/Volcanes.java::Volcanes.alRomperBloque", "--budget", "3000",
               "--allow-partial", "--json")
        t = b["text"]
        comprobar("bundle entrega el método pedido", "public void alRomperBloque(EventoRomper evento)" in t)
        comprobar("bundle incluye su anotación", "@SubscribeEvent" in t)
        comprobar("bundle sigue la llamada a otro archivo", "public static int calcularCalor(int profundidad)" in t)
        comprobar("bundle llega dos saltos (calcularCalor → limitar → CALOR_MAXIMO)",
                  "public static int limitar(int valor)" in t and "CALOR_MAXIMO = 1200" in t)
        b2 = cl(db, "bundle", str(raiz), "fundible roca", "--require",
                "src/main/java/es/ejemplo/volcanes/Roca.java::Roca.fundible", "--budget", "2000", "--allow-partial",
                "--json")
        comprobar("bundle incluye la constante de la clase que usa el método", "DUREZA_MAXIMA = 10" in b2["text"])
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print(f"\n{sum(RESULTADOS)}/{len(RESULTADOS)} comprobaciones de Java pasan")
    return 0 if all(RESULTADOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
