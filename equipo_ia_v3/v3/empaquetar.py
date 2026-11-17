#!/usr/bin/env python3
"""Equipo IA V3 — EMPAQUETADO (Etapa 8): un ZIP autocontenido, con manifiesto SHA-256, sin secretos ni modelos.

    python3 -B v3/empaquetar.py --salida DIR_NUEVO          (desde equipo_ia_v3/)

**Contenido** (dentro del ZIP, bajo `EquipoIA_V3_1/`):
- `equipo_ia_v3/`, sin cachés;
- `fuentes/codex_complementos/` y `fuentes/contexto_ligero_v35/`: las selecciones originales que la línea base
  necesita;
- `ORIGENES_SHA256.json`, `AGENTS.md` y `LEEME_PAQUETE.md`, este último generado;
- `MANIFIESTO_SHA256.json`, con el SHA-256 de cada archivo, también generado.

**Excluye SIEMPRE:**
- `GameAgentEngine/`, que es otro proyecto;
- `fuentes/claude_v2f1`, idéntica a `equipo_ia_v3/sistema/`;
- `.git`, bases SQLite, modelos GGUF, `__pycache__` y `*.pyc`.

**NO genera el ZIP** si encuentra enlaces simbólicos, archivos de más de 15 MB, patrones de credenciales (claves
privadas, tokens), direcciones de correo electrónico o **rutas personales**. Los datos privados no se empaquetan.

**Rutas personales (V3.1).** Son la carpeta personal de un usuario (`C:\\Users\\<nombre>`, `/home/<nombre>`,
`/Users/<nombre>`, salvo nombres genéricos como `user`) y, en esta máquina, la carpeta personal real y la carpeta de
trabajo que contiene el proyecto, en cualquiera de sus formas (nativa, POSIX, con «\\» escapadas, sin unidad).
- En los REGISTROS y la DOCUMENTACIÓN (`equipo_ia_v3/evidencias/`, `equipo_ia_v3/docs/`, `equipo_ia_v3/PROGRESO.md`),
  se sustituyen DENTRO DEL ZIP: la carpeta de trabajo por `<TRABAJO>` y cualquier carpeta personal por `<CASA>` (el
  archivo del disco no cambia; el manifiesto lleva el SHA-256 de lo empaquetado).
- Límite: una carpeta de trabajo que no sea un perfil de usuario solo se reconoce si es la ACTUAL (la que contiene el
  proyecto). Al empaquetar una copia movida a otra carpeta, las rutas de trabajo antiguas de sus registros no se
  detectan; por eso el paquete se genera siempre desde el árbol de trabajo original.
- En cualquier otro archivo (código, pruebas, `sistema/`, `fuentes/`, nombres de archivo) NO se sustituye nada: se
  rechaza el paquete, porque cambiar código o pruebas alteraría lo verificado.
- Si después de sustituir queda alguna ruta personal, también se rechaza.

**Reproducible:** las entradas van ordenadas, con fecha fija y permisos fijos. Junto al ZIP se escribe su
`.sha256`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]               # equipo_ia_v3/
REPO = RAIZ.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3.plataforma import es_enlace, variantes_ruta  # noqa: E402
PREFIJO = "EquipoIA_V3_1"
INCLUIR = [("equipo_ia_v3", RAIZ), ("fuentes/codex_complementos", REPO / "fuentes" / "codex_complementos"),
           ("fuentes/contexto_ligero_v35", REPO / "fuentes" / "contexto_ligero_v35")]
SUELTOS = [("ORIGENES_SHA256.json", REPO / "ORIGENES_SHA256.json"), ("AGENTS.md", REPO / "AGENTS.md")]
EXCLUIR_PARTES = {"__pycache__", ".git", "GameAgentEngine"}
EXCLUIR_SUFIJOS = (".pyc", ".sqlite3", ".sqlite", ".db", ".gguf", ".zip")
MAX_BYTES = 15 * 1024 * 1024
FECHA = (2026, 11, 10, 0, 0, 0)
SECRETOS = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|github_pat_\w{20,}"
                      r"|\bsk-[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{16}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}|\bAIza[0-9A-Za-z_-]{35}\b")
# Fixtures SINTÉTICAS conocidas, ligadas al SHA-256 EXACTO de su archivo: si el archivo cambia, vuelve a revisarse.
FIXTURES_SINTETICAS = {
    # test_pem_and_bearer_multiline: cabecera PEM con cuerpo «VALOR_PRIVADO» (13 caracteres, no es una clave) para
    # comprobar que Contexto Ligero REDACTA secretos; la prueba exige que «VALOR_PRIVADO» no aparezca en la salida.
    f"{PREFIJO}/fuentes/contexto_ligero_v35/tests/test_context_output.py": "1c53bec87e136a02c129c42aa02bb1aaace023e730dc3bac0f5753b9933792fc",
}
CORREO = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")

# --- Rutas personales (V3.1, mantenimiento) ---------------------------------------------------------------------
CASA, TRABAJO = "<CASA>", "<TRABAJO>"
ANONIMIZABLES = ("equipo_ia_v3/evidencias/", "equipo_ia_v3/docs/", "equipo_ia_v3/PROGRESO.md")
USUARIOS_GENERICOS = frozenset({"user", "public", "default", "default user", "all users", "<casa>", "<nombre>"})
_SEP = r"(?:\\+|/)"
PERFILES = (re.compile(rf"(?i)\b[a-z]:{_SEP}(?:users|documents and settings){_SEP}([^\\/\s\"'<>|*?:]{{1,64}})"),
            re.compile(rf"(?i)\\+users\\+([^\\/\s\"'<>|*?:]{{1,64}})\\"),       # recortada, sin unidad
            re.compile(r"(?<![\w.:/-])/(?:home|Users)/([A-Za-z0-9._-]{1,64})"))


def _formas(ruta: Path) -> list:
    """Formas en que `ruta` aparece en un texto: nativa, POSIX, «\\» escapadas una y dos veces, sin unidad y sin la
    barra inicial (trazas recortadas por el principio, p. ej. «carpeta\\\\de\\\\trabajo\\\\…»). Las recortadas solo
    cuentan si conservan al menos un separador: un nombre suelto de carpeta no se considera una ruta."""
    formas = set()
    for v in variantes_ruta(ruta):
        formas.update({v, v.replace("\\\\", "\\\\\\\\") if "\\\\" in v else v})
    sin_unidad = {f[2:] for f in formas if len(f) > 3 and f[1] == ":"}
    recortadas = sin_unidad | {f.lstrip("\\/") for f in formas | sin_unidad}
    return sorted(formas | {f for f in recortadas if len(f) > 4 and re.search(r"[\\/]", f)}, key=len, reverse=True)


def rutas_de_esta_maquina() -> list:
    """[(forma, marca)], la más larga primero: carpeta de trabajo (la que contiene el proyecto), la superior a ella
    si no es la raíz de una unidad, y la carpeta personal REAL."""
    pares = [(f, TRABAJO) for f in _formas(REPO.parent)] + [(f, CASA) for f in _formas(Path.home())]
    superior = REPO.parent.parent
    if superior != Path(superior.anchor):
        pares += [(f, TRABAJO + "/..") for f in _formas(superior)]
    return sorted(pares, key=lambda p: len(p[0]), reverse=True)


def anonimizar(texto: str, pares: list) -> str:
    """Rutas de esta máquina → marcas y, después, CUALQUIER carpeta personal (de cualquier usuario no genérico) →
    `<CASA>`: los procesos hijo pueden tener la carpeta personal redirigida, y un registro puede citar la de otro."""
    for forma, marca in pares:
        texto = texto.replace(forma, marca)
    for i, patron in enumerate(PERFILES):
        texto = patron.sub(lambda m: m.group(0) if m.group(1).strip().lower() in USUARIOS_GENERICOS
                           else CASA + ("\\" if i == 1 else ""), texto)
    return texto


def ruta_personal(texto: str, pares: list):
    """Primera ruta personal encontrada (recortada, para el mensaje) o None."""
    for forma, _ in pares:
        if forma in texto:
            return forma[:12] + "…"
    for patron in PERFILES:
        for m in patron.finditer(texto):
            if m.group(1).strip().lower() not in USUARIOS_GENERICOS:
                return m.group(0)[:12] + "…"
    return None


def datos_para_zip(nombre: str, datos: bytes, pares: list) -> bytes:
    """Lo que se empaqueta: los mismos bytes, salvo en registros y documentación (ANONIMIZABLES), donde las rutas de
    esta máquina se sustituyen por marcas. Determinista: mismo archivo → mismos bytes."""
    if not nombre[len(PREFIJO) + 1:].startswith(ANONIMIZABLES):
        return datos
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError:
        # 2026-11-17: registros de TEXTO con algún byte que no es UTF-8 (server.log): se anonimizan como latin-1, que
        # conserva cada byte. Los binarios (PNG…) no se tocan: cambiar bytes los rompería; si llevan rutas, recoger()
        # los rechaza.
        if not nombre.endswith(TEXTO_SUFIJOS):
            return datos
        texto = datos.decode("latin-1")
        nuevo = anonimizar(texto, pares)
        return datos if nuevo == texto else nuevo.encode("latin-1", errors="replace")
    nuevo = anonimizar(texto, pares)
    return datos if nuevo == texto else nuevo.encode("utf-8")


TEXTO_SUFIJOS = (".log", ".txt", ".json", ".jsonl", ".md", ".csv")


class Rechazo(Exception):
    """El contenido no se puede empaquetar: no se genera ningún ZIP."""


def recoger() -> list:
    """(ruta_en_zip, ruta_local) de todo lo que se incluye, en orden. Lanza Rechazo ante cualquier problema."""
    entradas, problemas = [], []
    for destino, origen in INCLUIR:
        for p in sorted(origen.rglob("*")):
            rel = p.relative_to(origen)
            if EXCLUIR_PARTES & set(rel.parts) or p.name.endswith(EXCLUIR_SUFIJOS):
                continue
            if es_enlace(p):                       # en Windows también uniones de directorio
                problemas.append(f"enlace simbólico: {destino}/{rel}")
                continue
            if p.is_file():
                entradas.append((f"{PREFIJO}/{destino}/{rel.as_posix()}", p))
    for destino, origen in SUELTOS:
        entradas.append((f"{PREFIJO}/{destino}", origen))
    pares = rutas_de_esta_maquina()
    for nombre, p in entradas:
        datos = p.read_bytes()
        r = ruta_personal(nombre, pares)
        if r is None:
            try:
                r = ruta_personal(datos_para_zip(nombre, datos, pares).decode("utf-8"), pares)
            except UnicodeDecodeError:
                # 2026-11-17: antes estos archivos (PNG con metadatos de Blender, registros con un byte raro…) se
                # saltaban la búsqueda y entraban con rutas de esta máquina. Ahora se buscan byte a byte, como latin-1
                # (nunca falla), DESPUÉS de anonimizar los de texto; en los binarios, una ruta hace que se rechacen.
                r = ruta_personal(datos_para_zip(nombre, datos, pares).decode("latin-1"), pares)
        if r is None and datos.count(b"\x00") > len(datos) // 4:
            # UTF-16 de Windows: con caracteres ASCII es UTF-8 «válido» (lleno de NUL) y la ruta no se ve
            r = ruta_personal(datos.decode("utf-16-le", errors="ignore"), pares)
        if r is not None:
            problemas.append(f"ruta personal ({r}): {nombre}")
        if len(datos) > MAX_BYTES:
            problemas.append(f"demasiado grande ({len(datos)} bytes): {nombre}")
        try:
            texto = datos.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if SECRETOS.search(texto) and FIXTURES_SINTETICAS.get(nombre) != hashlib.sha256(datos).hexdigest():
            problemas.append(f"posible credencial: {nombre}")
        m = CORREO.search(texto)
        if m:
            problemas.append(f"dirección de correo ({m.group(0)[:3]}…): {nombre}")
    if problemas:
        raise Rechazo("; ".join(problemas[:20]) + (f" … y {len(problemas) - 20} más" if len(problemas) > 20 else ""))
    return entradas


def leeme(n: int) -> str:
    return (f"# Equipo IA V3.1 (F0.5, portabilidad): paquete autocontenido\n\nContiene {n} archivos con su SHA-256 "
            "en `MANIFIESTO_SHA256.json`. Empiece por `equipo_ia_v3/LEEME_V3.md`, `equipo_ia_v3/PROGRESO.md` y "
            "`equipo_ia_v3/docs/V31_F05_PORTABILIDAD.md`.\n\n"
            "Verificación (Windows: `py` en lugar de `python3`):\n\n```sh\ncd EquipoIA_V3_1/equipo_ia_v3\n"
            "python3 -B verificar_v3.py --completo\n```\n\n"
            "NO listo para producción: agentes SIMULADOS; nada se ha validado con Qwen real. Plataformas: Windows 11 "
            "verificado con V3.1 F0.5; Linux verificado con V3 (Etapa 8) pero NO vuelto a ejecutar con V3.1; WSL2 y "
            "Android/Termux sin validar (ver `docs/INVENTARIO_FUNCIONES.md`). La ejecución de código generado sigue "
            "DESHABILITADA (SEG-01). No contiene modelos, bases de datos, secretos ni datos privados. No incluye "
            "GameAgentEngine.\n")


def _anadir(z: zipfile.ZipFile, nombre: str, datos: bytes) -> None:
    info = zipfile.ZipInfo(nombre, date_time=FECHA)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o644 & 0xFFFF) << 16
    z.writestr(info, datos)


def empaquetar(salida: Path) -> dict:
    entradas = recoger()
    pares = rutas_de_esta_maquina()
    contenido = {nombre: datos_para_zip(nombre, p.read_bytes(), pares) for nombre, p in entradas}
    manifiesto = {nombre[len(PREFIJO) + 1:]: hashlib.sha256(d).hexdigest() for nombre, d in contenido.items()}
    zip_ruta = salida / f"{PREFIJO}.zip"
    with zipfile.ZipFile(zip_ruta, "x") as z:
        for nombre, _ in entradas:
            _anadir(z, nombre, contenido[nombre])
        _anadir(z, f"{PREFIJO}/LEEME_PAQUETE.md", leeme(len(entradas)).encode("utf-8"))
        _anadir(z, f"{PREFIJO}/MANIFIESTO_SHA256.json",
                (json.dumps(manifiesto, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    h = hashlib.sha256(zip_ruta.read_bytes()).hexdigest()
    (salida / f"{PREFIJO}.zip.sha256").write_text(f"{h}  {PREFIJO}.zip\n", encoding="utf-8")
    return {"zip": str(zip_ruta), "sha256": h, "archivos": len(entradas) + 2, "bytes": zip_ruta.stat().st_size}


def extraer_seguro(zip_ruta: Path, destino: Path) -> None:
    """Extrae comprobando cada nombre (sin rutas absolutas, sin «..», sin enlaces)."""
    with zipfile.ZipFile(zip_ruta) as z:
        for i in z.infolist():
            p = Path(i.filename)
            if p.is_absolute() or ".." in p.parts or (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise Rechazo(f"entrada ZIP insegura: {i.filename}")
        z.extractall(destino)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True, help="directorio NUEVO donde escribir el ZIP")
    a = ap.parse_args(argv)
    try:
        a.salida.mkdir(parents=True, exist_ok=False)
    except OSError as e:
        print("salida rechazada (debe ser un directorio nuevo):", e)
        return 2
    try:
        r = empaquetar(a.salida)
    except Rechazo as e:
        print(f"=== PAQUETE RECHAZADO: {e} ===")
        return 1
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
