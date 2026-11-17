"""V2-E.2: INTERFACES para capacidades futuras (no implementadas salvo lo indicado).

  * Complementos de lenguaje: Python (solo análisis estático); Java, C++, C#, JavaScript y Rust
    declarados y NO implementados. Ningún complemento ejecuta pruebas (Modo B deshabilitado).
  * Evaluación de migraciones entre lenguajes: solo la interfaz y una lista de comprobación.
  * Candidatos y versiones archivadas: modelo de datos e interfaz del repositorio.
  * Configuración modular: validación estricta; nunca puede activar la ejecución real.
La interfaz gráfica y Windows 11 se apoyan en los archivos JSON de estado y en plataforma.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import analisis_estatico, config


class NoImplementado(NotImplementedError):
    pass


class EjecucionDeshabilitada(PermissionError):
    pass


class PluginLenguaje:
    nombre = "base"
    extensiones = ()
    estado = "no_implementado"          # | "estatico" (solo análisis estático)

    def analizar_estatico(self, archivos: dict) -> dict:
        raise NoImplementado(f"análisis estático de {self.nombre} no implementado")

    def ejecutar_pruebas(self, *_a, **_k):
        raise EjecucionDeshabilitada("la ejecución de pruebas está deshabilitada (Modo B)")


class PluginPython(PluginLenguaje):
    nombre, extensiones, estado = "python", (".py",), "estatico"

    def analizar_estatico(self, archivos):
        return analisis_estatico.analizar({k: v for k, v in archivos.items() if k.endswith(".py")})


def _stub(nombre_, ext):
    return type(f"Plugin_{nombre_}", (PluginLenguaje,), {"nombre": nombre_, "extensiones": ext})


REGISTRO = {p.nombre: p for p in (PluginPython(), _stub("java", (".java",))(),
                                  _stub("cpp", (".cpp", ".cc", ".hpp", ".h"))(), _stub("csharp", (".cs",))(),
                                  _stub("javascript", (".js", ".mjs"))(), _stub("rust", (".rs",))())}


def plugin_para(ruta: str) -> PluginLenguaje | None:
    for p in REGISTRO.values():
        if any(ruta.endswith(e) for e in p.extensiones):
            return p
    return None


class EvaluadorMigracion:
    """Interfaz. evaluar() devuelve una lista de comprobación; la evaluación real no existe aún."""
    LISTA = ("inventario de archivos y dependencias", "equivalencia de tipos y bibliotecas",
             "pruebas de caracterización en el lenguaje de origen (requieren ejecución real)",
             "migración parcial por módulos con interfaz estable", "comparación de resultados")

    def evaluar(self, origen: str, destino: str, archivos: dict) -> dict:
        for l in (origen, destino):
            if l not in REGISTRO:
                raise ValueError(f"lenguaje desconocido: {l}")
        return {"estado": "no_implementado", "origen": origen, "destino": destino, "viable": None,
                "archivos": len(archivos), "lista_de_comprobacion": list(self.LISTA),
                "nota": "sin ejecución real no se puede evaluar la equivalencia"}


ESTADOS_CANDIDATO = ("candidato", "archivado", "descartado")


@dataclass(frozen=True)
class Candidato:
    id: str
    version_base: str
    descripcion: str
    estado: str = "candidato"
    sha256_conjunto: str = ""

    def __post_init__(self):
        if self.estado not in ESTADOS_CANDIDATO:
            raise ValueError("estado de candidato inválido")


class RepositorioCandidatos:
    """Interfaz para versiones archivadas y candidatos independientes (sin implementación)."""

    def proponer(self, candidato: Candidato):
        raise NoImplementado("repositorio de candidatos")

    def archivar(self, cid: str):
        raise NoImplementado("repositorio de candidatos")

    def comparar(self, a: str, b: str):
        raise NoImplementado("repositorio de candidatos")


CLAVES_CONFIG = {"incidencias": bool, "laboratorio": bool, "plugins": tuple, "interfaz": str}
PROHIBIDAS = ("ejecucion_real", "modo_b", "red", "privilegios", "instalar_dependencias")


@dataclass(frozen=True)
class ConfiguracionModular:
    incidencias: bool = True
    laboratorio: bool = True
    plugins: tuple = ("python",)
    interfaz: str = "cli"
    ejecucion_real: bool = field(default=False, init=False)

    @classmethod
    def desde_dict(cls, d: dict) -> "ConfiguracionModular":
        for k in d:
            if k in PROHIBIDAS:
                raise PermissionError(f"la configuración no puede activar '{k}'")
            if k not in CLAVES_CONFIG:
                raise ValueError(f"clave de configuración desconocida: {k}")
        v = dict(d)
        if "plugins" in v:
            v["plugins"] = tuple(v["plugins"])
            for p in v["plugins"]:
                if p not in REGISTRO:
                    raise ValueError(f"complemento desconocido: {p}")
        if v.get("interfaz", "cli") not in ("cli",):
            raise NoImplementado("solo existe la interfaz CLI")
        for k, t in CLAVES_CONFIG.items():
            if k in v and not isinstance(v[k], t):
                raise ValueError(f"tipo inválido para {k}")
        c = cls(**v)
        if c.ejecucion_real or config.MODO_B_HABILITADO:
            raise PermissionError("la ejecución real no puede activarse desde la configuración")
        return c
