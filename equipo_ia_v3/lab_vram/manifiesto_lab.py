"""Escribe el manifiesto SHA-256 de la carpeta de LABORATORIO CUDA+Vulkan.

    python -B lab_vram/manifiesto_lab.py CARPETA_VULKAN_EXTRAIDA DESTINO.json

Los archivos de la compilación CUDA toman su SHA-256 del registro verificado de F1 (`eq3/externos_f1.json`); el único
archivo nuevo, `ggml-vulkan.dll`, toma el suyo de la carpeta extraída del ZIP oficial de Vulkan, cuyo SHA-256 coincidió
con el que publica GitHub para la misma versión (b12110).
"""
import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
reg = json.loads((RAIZ / "eq3" / "externos_f1.json").read_text(encoding="utf-8"))
vulkan = Path(sys.argv[1]) / "ggml-vulkan.dll"
sha = {n: d["sha256"] for n, d in reg["llama"]["archivos"].items()}
sha["ggml-vulkan.dll"] = hashlib.sha256(vulkan.read_bytes()).hexdigest()
datos = {"origen": {"cuda": "registro eq3/externos_f1.json (llama-b12110-bin-win-cuda-12.4-x64.zip + cudart)",
                    "ggml-vulkan.dll": "llama-b12110-bin-win-vulkan-x64.zip, sha256 9732a5e48887ca54d0bfe4af4324dc85fd"
                                       "56cd8cda19b52df3542fa6ebe6874f (coincide con el digest de la API de GitHub; "
                                       "subido por github-actions[bot])"},
         "nota": "Carpeta de LABORATORIO: no la usa V2-F.1 ni la configuración estable.", "sha256": sha}
Path(sys.argv[2]).write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(sha), "archivos")
