"""Pruebas de la herramienta de mutación (auditoría de la Etapa 7: AUD-01 y AUD-02).

Una especificación es un DATO. No debe poder:
- ejecutar órdenes arbitrarias (AUD-01);
- escribir fuera de su espejo, ni a través de los enlaces a `sistema/` o `fuentes/` (AUD-02).
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3))
import mutacion as MU  # noqa: E402

BASE = {"descripcion": "prueba", "orden": ["{python}", "-B", "-m", "unittest", "discover", "-s", "v3/tests", "-t",
                                          "v3/tests", "-p", "test_linea_base.py"],
        "copiar": ["v3"], "enlazar": ["sistema"], "mutaciones": []}


class TestEspecificacionSegura(unittest.TestCase):
    def _spec(self, **cambios):
        d = tempfile.TemporaryDirectory(prefix="eq3_mu_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "spec.json"
        p.write_text(json.dumps(dict(BASE, **cambios)), encoding="utf-8")
        return p

    def test_orden_arbitraria_rechazada(self):
        for orden in (["sh", "-c", "echo x"], ["{python}", "-c", "print(1)"],
                      ["{python}", "-B", "-m", "unittest", "discover", "-s", "v3/tests; rm -rf /"],
                      ["{python}", "-B", "-m", "pip", "install", "x"]):
            with self.subTest(orden=orden):
                self.assertEqual(MU.main([str(self._spec(orden=orden))]), 2)

    def test_archivo_fuera_del_espejo_o_enlazado_rechazado(self):
        sistema = MU.RAIZ / "sistema" / "src" / "eq2" / "config.py"
        antes = hashlib.sha256(sistema.read_bytes()).hexdigest()
        for archivo in ("../../fuera.py", "/etc/passwd", "sistema/src/eq2/config.py", "fuentes/x.py", "v3/../../x.py"):
            with self.subTest(archivo=archivo):
                m = {"id": "M", "archivo": archivo, "antes": "MODO_B_HABILITADO = False",
                     "despues": "MODO_B_HABILITADO = True", "motivo": "prueba"}
                self.assertEqual(MU.main([str(self._spec(mutaciones=[m]))]), 2)
        self.assertEqual(hashlib.sha256(sistema.read_bytes()).hexdigest(), antes)    # el sistema real, intacto

    def test_primera_capa_validar_directamente(self):
        # Dos capas (validar() y la comprobación del destino en el espejo): cada una se prueba por separado.
        for archivo in ("sistema/src/eq2/config.py", "fuentes/x.py"):
            spec = dict(BASE, mutaciones=[{"id": "M", "archivo": archivo, "antes": "a", "despues": "b", "motivo": "m"}])
            with self.subTest(archivo=archivo), self.assertRaisesRegex(ValueError, "solo se mutan archivos COPIADOS"):
                MU.validar(spec)
        for mala in ("../x.py", "/etc/passwd", "a/../../b", ""):
            with self.subTest(ruta=mala), self.assertRaises(ValueError):
                MU._relativa(mala, "prueba")
        with self.assertRaisesRegex(ValueError, "AUD-01"):
            MU.validar(dict(BASE, orden=["{python}", "-B", "-m", "pip", "install", "x"]))
        MU.validar(BASE)                                                       # la especificación correcta pasa

    def test_copiar_y_enlazar_validados(self):
        self.assertEqual(MU.main([str(self._spec(copiar=["../fuera"]))]), 2)
        self.assertEqual(MU.main([str(self._spec(enlazar=["/etc"]))]), 2)
        for mala in (["GameAgentEngine"], ["../AGENTS.md"], ["fuentes/x.txt"], ["no_existe.md"]):
            with self.subTest(copiar_raiz=mala):
                self.assertEqual(MU.main([str(self._spec(copiar_raiz=mala))]), 2)


if __name__ == "__main__":
    unittest.main()
