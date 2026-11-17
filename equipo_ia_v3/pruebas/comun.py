"""Utilidades compartidas por las pruebas de eq3 (no es un módulo de pruebas: unittest no lo descubre)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SISTEMA = RAIZ / "sistema"
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import plataforma  # noqa: E402


def demo(tmp: Path, *extra) -> Path:
    """Ejecuta una demo REAL del código de V2-F.1 (agentes SIMULADOS por guion) en un laboratorio nuevo."""
    tmp.mkdir(parents=True)                       # V2-F.1 exige que su TMPDIR exista
    r = plataforma.ejecutar(plataforma.orden_eq2("equipo.py", "demo", "funcion", *extra), cwd=SISTEMA,
                            env=plataforma.entorno_hijo(tmp), timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"demo de V2-F.1 fallida: {r.stdout[-500:]} {r.stderr[-500:]}")
    return tmp / "equipo_f2" / "lab_v2f1"


def enlazar_o_omitir(caso, destino, objetivo) -> str:
    """Crea el enlace de una prueba de seguridad, o la marca OMITIDA (nunca OK) si la plataforma no lo permite."""
    try:
        return plataforma.crear_enlace(destino, objetivo)
    except plataforma.EnlaceNoDisponible as e:
        caso.skipTest(f"PLATAFORMA: {e}")


def union_o_omitir(caso, destino, objetivo_dir) -> None:
    """Crea una UNIÓN de directorio (junction) de Windows; fuera de Windows no existen y la prueba se omite."""
    if not plataforma.WINDOWS:
        caso.skipTest("PLATAFORMA: las uniones de directorio solo existen en Windows")
    import _winapi
    _winapi.CreateJunction(str(Path(objetivo_dir).resolve(strict=True)), str(destino))
