"""V3.1 F1-VRAM-EXP-V4.4 — vigilancia térmica de la GPU (solo LECTURA con `nvidia-smi`).

Nunca toca potencia, frecuencias, ventiladores ni límites. Dos usos:

- **Enfriar antes de cada petición** (`enfriar`): espera a que la GPU esté a ≤ `T_REANUDAR` y sin freno térmico de software,
  con una espera máxima `MAX_ENFRIAR_S`; si no se alcanza, es crítico (aborto seguro).
- **Vigilar durante TODA la evaluación** (hilo propio, cada `INTERVALO_S`): si aparece algo crítico, `critico` deja de ser
  None y el vigía de la tarea corta la petición en curso (misma vía que el tope de VRAM, `parar()` de V2-F.1), así que
  una generación larga no puede eludirla.

Crítico (parada inmediata):
  - freno térmico de HARDWARE o cualquier freno de hardware (`hw_slowdown`, incluye el freno de potencia);
  - temperatura ≥ `T_CRITICA`;
  - freno térmico de SOFTWARE continuo ≥ `MAX_FRENO_SW_S`;
  - fallo de supervisión: `MAX_FALLOS_LECTURA` lecturas seguidas sin temperatura, o el hilo muerto.
Lo que el sensor no da (p. ej. `power.draw` = [N/A] en esta RTX 3050) queda como None: no se inventa.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

# Umbrales (justificación en docs/V31_F1_VRAM_EXP_V4_4.md; RTX 3050 8 GB: objetivo 83 °C, máx. operación 92 °C,
# freno de hardware 94 °C, apagado 97 °C, leídos con `nvidia-smi -q -d TEMPERATURE`)
T_REANUDAR = 60          # antes de CADA petición
MAX_ENFRIAR_S = 180      # espera máxima para llegar a T_REANUDAR
T_AVISO = 80             # solo se anota (pico de una petición)
T_CRITICA = 88           # objetivo + 5: la regulación del controlador no lo contuvo; 4 °C por debajo del máximo
MAX_FRENO_SW_S = 20      # ≈ una generación entera regulando sin parar
MAX_FALLOS_LECTURA = 3   # ≈ 3 s sin temperatura = supervisión ciega
INTERVALO_S = 1.0

CAMPOS = ("temperature.gpu", "clocks_throttle_reasons.hw_thermal_slowdown",
          "clocks_throttle_reasons.sw_thermal_slowdown", "clocks_throttle_reasons.hw_slowdown",
          "clocks_throttle_reasons.hw_power_brake_slowdown", "clocks_throttle_reasons.active", "clocks.sm",
          "clocks.mem", "fan.speed", "pstate", "utilization.gpu", "memory.used", "power.draw")
CLAVES = ("temp_C", "freno_hw_termico", "freno_sw_termico", "freno_hw", "freno_hw_potencia", "motivos_activos",
          "reloj_sm_MHz", "reloj_mem_MHz", "ventilador_pct", "pstate", "uso_pct", "vram_MiB", "potencia_W")


def _valor(clave, s):
    s = s.strip()
    if not s or s.startswith("[") or s.upper() in ("N/A", "[N/A]", "NOT SUPPORTED"):
        return None
    if clave.startswith("freno"):
        return {"Active": True, "Not Active": False}.get(s)
    if clave in ("motivos_activos", "pstate"):
        return s
    try:
        return float(s) if clave == "potencia_W" else int(float(s))
    except ValueError:
        return None


def parsear(linea: str) -> dict:
    partes = linea.strip().split(",")
    if len(partes) != len(CLAVES):
        return {"error": f"formato: {len(partes)} campos"}
    return {k: _valor(k, v) for k, v in zip(CLAVES, partes)}


def leer_gpu(ejecutar=subprocess.run) -> dict:
    try:
        r = ejecutar(["nvidia-smi", f"--query-gpu={','.join(CAMPOS)}", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True, timeout=10)
        lineas = (r.stdout or "").strip().splitlines()
        return parsear(lineas[0]) if lineas else {"error": "sin salida"}
    except Exception as e:                                       # sin sensor: se anota, no se inventa
        return {"error": f"{type(e).__name__}: {e}"}


class Termica:
    """Estado térmico compartido por toda la evaluación. `leer` y `reloj` se inyectan en las pruebas."""

    def __init__(self, registro: Path | None = None, leer=leer_gpu, reloj=time.monotonic, intervalo=INTERVALO_S):
        self.registro, self.leer, self.reloj, self.intervalo = registro, leer, reloj, intervalo
        self.ultima, self.critico, self.maxima, self.fallos, self.pico = None, None, None, 0, None
        self.freno_sw_desde, self.freno_sw_total_s, self.lecturas = None, 0.0, 0
        self._fin, self._hilo, self._t_ant = threading.Event(), None, None
        self.lock = threading.Lock()

    # --- una lectura ---
    def muestrear(self) -> dict:
        lec = self.leer()
        t = self.reloj()
        lec = dict(lec) | {"t": time.strftime("%H:%M:%S"), "mono": round(t, 2)}
        with self.lock:
            self.lecturas += 1
            self.ultima = lec
            temp = lec.get("temp_C")
            if temp is None:
                self.fallos += 1
                if self.fallos >= MAX_FALLOS_LECTURA:
                    self._marcar(f"fallo_supervision_{self.fallos}_lecturas_sin_temperatura")
            else:
                self.fallos = 0
                self.maxima = max(self.maxima or temp, temp)
                self.pico = max(self.pico or temp, temp)
                if lec.get("freno_hw_termico"):
                    self._marcar("freno_termico_hardware")
                elif lec.get("freno_hw") or lec.get("freno_hw_potencia"):
                    self._marcar("freno_hardware")
                elif temp >= T_CRITICA:
                    self._marcar(f"temperatura_{temp}C")
            if lec.get("freno_sw_termico"):
                if self.freno_sw_desde is None:
                    self.freno_sw_desde = t
                elif self._t_ant is not None:
                    self.freno_sw_total_s += t - self._t_ant
                if t - self.freno_sw_desde >= MAX_FRENO_SW_S:
                    self._marcar(f"freno_termico_software_{round(t - self.freno_sw_desde)}s")
            else:
                self.freno_sw_desde = None
            self._t_ant = t
        if self.registro is not None:
            try:
                with self.registro.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(lec | ({"critico": self.critico} if self.critico else {})) + "\n")
            except OSError:
                pass
        return lec

    def _marcar(self, motivo):
        if self.critico is None:
            self.critico = motivo

    def marcar_critico(self, motivo):
        with self.lock:
            self._marcar(motivo)

    # --- hilo ---
    def iniciar(self):
        def bucle():
            while not self._fin.is_set():
                try:
                    self.muestrear()
                except Exception as e:                           # nunca muere en silencio: queda crítico
                    self.marcar_critico(f"fallo_supervision_{type(e).__name__}")
                self._fin.wait(self.intervalo)
        self._hilo = threading.Thread(target=bucle, daemon=True, name="eq3-termica-v4-4")
        self._hilo.start()
        return self

    def detener(self) -> dict:
        self._fin.set()
        if self._hilo:
            self._hilo.join(10)
        return self.resumen()

    def motivo_parada(self):
        """Lo que consulta el vigía en CADA `parar()`: crítico, o el hilo muerto sin haberlo detenido."""
        if self.critico:
            return self.critico
        if self._hilo is not None and not self._hilo.is_alive() and not self._fin.is_set():
            self.marcar_critico("fallo_supervision_hilo_muerto")
            return self.critico
        return None

    def resumen(self) -> dict:
        return {"critico": self.critico, "temp_maxima_C": self.maxima, "lecturas": self.lecturas,
                "freno_sw_total_s": round(self.freno_sw_total_s, 1), "ultima": self.ultima}

    # --- antes de cada petición ---
    def enfriar(self, dormir=time.sleep) -> dict:
        """Espera a ≤ T_REANUDAR y sin freno de software. Devuelve {ok, enfriamiento_s, temp_inicio_C, temp_fin_C}."""
        t0 = self.reloj()
        lec = self.muestrear()
        inicio = lec.get("temp_C")
        while True:
            m = self.motivo_parada()
            if m:
                return {"ok": False, "motivo": m, "enfriamiento_s": round(self.reloj() - t0, 2),
                        "temp_inicio_C": inicio, "temp_fin_C": lec.get("temp_C")}
            temp = lec.get("temp_C")
            if temp is not None and temp <= T_REANUDAR and not lec.get("freno_sw_termico"):
                self.pico = temp                                  # el pico de la PRÓXIMA petición empieza aquí
                return {"ok": True, "enfriamiento_s": round(self.reloj() - t0, 2), "temp_inicio_C": inicio,
                        "temp_fin_C": temp}
            if self.reloj() - t0 >= MAX_ENFRIAR_S:
                self.marcar_critico(f"enfriamiento_no_alcanzado_{temp}C_en_{MAX_ENFRIAR_S}s")
                continue
            dormir(self.intervalo)
            lec = self.muestrear()
