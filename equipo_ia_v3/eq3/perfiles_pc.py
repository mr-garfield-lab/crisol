"""Equipo IA V3 · PERFILES DE PC (Etapa 6): planificación de recursos de llama-server para el PC del usuario.

**El equipo se DECLARA, no se detecta:** este contenedor no es ese PC. Es Windows 11 con un AMD Ryzen 5 5600
(6 núcleos y 12 hilos), 32 GB de RAM y una NVIDIA RTX 3050 de 8 GB.

- **Un solo modelo para los tres agentes.** Sirve a A1, A2 y A3 por TURNOS (`--parallel 1`), igual que en
  V2-F.1: tres agentes no requieren tres modelos simultáneos.
- **Límite externo.** El presupuesto de 6144 MiB del AI Lab Coordinator se toma como TOPE de VRAM para Equipo
  IA. Aquí solo se LEE: no se modifica ni se integra con ese proyecto.
- **Solo estimaciones.** Pesos proporcionales a las capas que van a la GPU, más la caché KV en f16, más un
  margen. Hay que validarlas en el PC real (`nvidia-smi`, registro de llama-server).
- **Sin descargas.** Con la ruta de un GGUF EXISTENTE se usa su tamaño real (`stat`, sin leer el contenido); sin
  ella, el del catálogo, que es APROXIMADO.
- **Sin ejecución.** Este módulo nunca lanza nada: solo devuelve la orden propuesta como lista de argumentos,
  sin shell y con el servidor solo en `127.0.0.1`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .plataforma import es_enlace

MIB = 1024 * 1024
CTX_PC = (2048, 4096, 8192, 16384)
SOBRECARGA_FIJA_MIB = 300            # búferes de cálculo y de CUDA: ESTIMACIÓN
SOBRECARGA_PROPORCIONAL = 0.05
PROCESO_RAM_MIB = 1024
NATURALEZA = "ESTIMACIÓN: no validada en el PC real (validar con nvidia-smi y el registro de llama-server)"


@dataclass(frozen=True)
class Modelo:
    nombre: str
    archivo_mib: int
    capas: int
    kv_dim: int                       # n_head_kv × head_dim (atención agrupada)
    fuente: str = "catálogo aproximado"


@dataclass(frozen=True)
class Equipo:
    nombre: str
    nucleos: int
    hilos: int
    ram_mib: int
    vram_mib: int
    reserva_vram_mib: int             # escritorio de Windows y otras aplicaciones: ESTIMACIÓN
    reserva_ram_mib: int
    limite_coordinador_mib: int       # AI Lab Coordinator: solo se lee


# Valores APROXIMADOS de la familia Qwen2.5-Coder en Q4_K_M (configuración publicada de cada modelo y tamaño
# habitual del GGUF). No se ha descargado ninguno; con la ruta de un archivo real se usa su tamaño.
CATALOGO = {
    "qwen2.5-coder-3b-q4_k_m": Modelo("Qwen2.5-Coder-3B-Instruct Q4_K_M", 1840, 36, 256),
    "qwen2.5-coder-7b-q4_k_m": Modelo("Qwen2.5-Coder-7B-Instruct Q4_K_M", 4460, 28, 512),
    "qwen2.5-coder-14b-q4_k_m": Modelo("Qwen2.5-Coder-14B-Instruct Q4_K_M", 8570, 48, 1024),
}
PC_USUARIO = Equipo("PC del usuario (declarado): Ryzen 5 5600, 32 GB, RTX 3050 8 GB, Windows 11",
                    nucleos=6, hilos=12, ram_mib=32768, vram_mib=8192, reserva_vram_mib=1024,
                    reserva_ram_mib=8192, limite_coordinador_mib=6144)


def kv_mib(modelo: Modelo, ctx: int) -> float:
    """Caché KV en f16: K y V × capas × contexto × kv_dim × 2 bytes."""
    return 2 * modelo.capas * ctx * modelo.kv_dim * 2 / MIB


def con_archivo(modelo: Modelo, ruta: Path) -> Modelo:
    """El mismo modelo con el tamaño REAL de un GGUF existente. Solo `stat`: no lee ni carga nada."""
    p = Path(ruta)
    if p.suffix.lower() != ".gguf" or not p.is_file() or es_enlace(p):
        raise ValueError(f"se espera un archivo .gguf normal existente: {ruta}")
    return Modelo(modelo.nombre, max(1, round(p.stat().st_size / MIB)), modelo.capas, modelo.kv_dim,
                  fuente=f"tamaño real de {p.name}")


def _necesidad(modelo: Modelo, ctx: int, capas_gpu: int) -> tuple:
    frac = capas_gpu / modelo.capas
    pesos, kv = modelo.archivo_mib, kv_mib(modelo, ctx)
    vram = (pesos + kv) * frac + ((SOBRECARGA_FIJA_MIB + SOBRECARGA_PROPORCIONAL * pesos) if capas_gpu else 0)
    ram = (pesos + kv) * (1 - frac) + PROCESO_RAM_MIB
    return round(vram), round(ram)


def planificar(modelo: Modelo, ctx: int, equipo: Equipo = PC_USUARIO, ruta_modelo: str = "modelo.gguf",
               puerto: int = 8080) -> dict:
    """Plan de UN servidor compartido por A1/A2/A3: capas en la GPU, memoria estimada y la orden propuesta."""
    if ctx not in CTX_PC:
        raise ValueError(f"contexto no admitido: {ctx} (admitidos: {CTX_PC})")
    if not 1024 <= int(puerto) <= 65535:
        raise ValueError("puerto fuera de rango")
    if any(c in str(ruta_modelo) for c in "\n\r\0"):
        raise ValueError("ruta de modelo con caracteres de control")
    tope_vram = min(equipo.vram_mib - equipo.reserva_vram_mib, equipo.limite_coordinador_mib)
    tope_ram = equipo.ram_mib - equipo.reserva_ram_mib
    capas_gpu = next(c for c in range(modelo.capas, -1, -1) if _necesidad(modelo, ctx, c)[0] <= tope_vram)
    vram, ram = _necesidad(modelo, ctx, capas_gpu)
    avisos = []
    if capas_gpu == 0:
        avisos.append("sin capas en la GPU: todo en la CPU (lento)")
    elif capas_gpu < modelo.capas:
        avisos.append(f"descarga parcial: {capas_gpu} de {modelo.capas} capas en la GPU; el resto en la CPU (más lento)")
    if modelo.fuente == "catálogo aproximado":
        avisos.append("tamaño del modelo según el catálogo aproximado: indica la ruta del GGUF real")
    cabe = ram <= tope_ram
    if not cabe:
        avisos.append(f"RAM insuficiente: se estiman {ram} MiB y hay {tope_ram} MiB disponibles tras la reserva")
    argv = ["llama-server", "-m", str(ruta_modelo), "--host", "127.0.0.1", "--port", str(int(puerto)),
            "-c", str(ctx), "-ngl", str(capas_gpu), "-t", str(equipo.nucleos), "--parallel", "1"]
    return {"modelo": modelo.nombre, "fuente_tamano": modelo.fuente, "ctx": ctx, "capas_gpu": capas_gpu,
            "capas": modelo.capas, "vram_estimada_mib": vram, "tope_vram_mib": tope_vram,
            "ram_estimada_mib": ram, "tope_ram_mib": tope_ram, "kv_mib": round(kv_mib(modelo, ctx)),
            "cabe": cabe, "agentes": ["A1", "A2", "A3"], "servidores": 1, "turnos": "secuenciales (--parallel 1)",
            "hilos": equipo.nucleos, "argv": argv, "avisos": avisos, "naturaleza": NATURALEZA}


def recomendar(equipo: Equipo = PC_USUARIO, ctx: int = 8192) -> dict:
    """El modelo más capaz del catálogo que cabe ENTERO en la GPU con ese contexto, y todos los planes."""
    planes = {k: planificar(m, ctx, equipo) for k, m in CATALOGO.items()}
    enteros = [k for k, p in planes.items() if p["cabe"] and p["capas_gpu"] == p["capas"]]
    mejor = max(enteros, key=lambda k: CATALOGO[k].archivo_mib) if enteros else None
    return {"equipo": equipo.nombre, "ctx": ctx, "recomendado": mejor, "planes": planes, "naturaleza": NATURALEZA}
