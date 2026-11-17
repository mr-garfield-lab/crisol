"""Pruebas de V3.1 F1-V5.1 (`eq3/evaluar_f1_v5_1.py`): el eco verificado de la continuación (el aborto de T08), los 6 cerebros,
el descanso al empezar un bloque y las comprobaciones previas. Sin GPU ni modelo: los backends son simulados y nada generado
se ejecuta.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_evaluar_f1_v5_1.py -v
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import comun  # noqa: F401
import aux_procedencia_v4_3 as A
from eq2 import inferencia
from eq3 import evaluar_f1 as EV
from eq3 import evaluar_f1_v5 as V5
from eq3 import evaluar_f1_v5_1 as V
from eq3 import evaluar_f1_vram_exp_v4_5_1 as B

TAREAS, ORACULOS = EV.E.cargar()
LITERAL = repr(["a", "b", "c", "e"])                          # T08.esperado tal como lo escribe Python
A1_T08 = f"ARCHIVO: solucion.py\n\n```python\ndef respuesta():\n    return {LITERAL}\n```\n\nFIN"
A3_CORTADA = f"CASO: respuesta() == {LITERAL} | EV1, EV2, EV3\nPROBLEMA: P1 | La lista"
A3_RESTO = " devuelta cumple la tarea.\nFIN"


def _tmp(caso) -> Path:
    d = Path(tempfile.mkdtemp(prefix="f1t51_"))
    caso.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
    return d


class GuionCorte(A.Guion):
    """Como el guion de V4.3, pero A3 se corta por el tope (finish_reason = length) y el servidor admite continuación:
    V2-F.1 reenvía el prompt + un mensaje «assistant» con la respuesta cortada, igual que en T08."""
    etiqueta = "GUION_V5_1"

    def __init__(self, cortar=True, **kw):
        super().__init__(**kw)
        self.soporta_continuacion, self.cortar, self.mensajes_vistos = True, cortar, []

    def completar(self, mensajes, max_tokens, plazo_s):
        self.mensajes_vistos.append(mensajes)
        sis = str(mensajes[0].get("content", "")) if mensajes else ""
        agente = next((a for a in ("A1", "A2", "A3") if f"Eres {a}" in sis), "A1")
        con_eco = bool(mensajes) and mensajes[-1].get("role") == "assistant"
        if agente == "A3" and self.cortar:
            texto, fin = (A3_RESTO, "stop") if con_eco else (A3_CORTADA, "length")
        else:
            texto, fin = self.respuestas[agente], "stop"
        self.prompts.append("\n".join(str(m.get("content", "")) for m in mensajes))
        self.salidas.append(texto)
        self.peticiones.append({"status": 200, "metricas": {"prompt_n": 10, "predicted_n": 5},
                                "sha256": hashlib.sha256(texto.encode()).hexdigest()})
        return inferencia.Respuesta(texto=texto, tokens_prompt=10, tokens_gen=5, finish_reason=fin)


def correr(caso, protector, cortar=True, respuestas=None):
    EV.preparar_contexto()
    be = GuionCorte(cortar=cortar, respuestas={"A1": A1_T08, "A2": "VEREDICTO: aceptable"} | (respuestas or {}))
    vig = EV.Vigia(medir=lambda: None, intervalo=0.05).iniciar()
    try:
        with protector("E3"):
            return EV.ejecutar_tarea("E3", TAREAS["T08"], ORACULOS["T08"], ORACULOS, _tmp(caso) / "E3", lambda: be,
                                     vig), be
    finally:
        vig.detener()


class TestEcoDeLaContinuacion(unittest.TestCase):
    def test_v4_3_reproduce_el_falso_positivo_de_t08(self):
        with self.assertRaises(EV.FugaDeOraculo) as e:
            correr(self, B._protector_v43)
        self.assertIn("T08.esperado", str(e.exception))

    def test_v5_1_deja_pasar_el_eco_exacto(self):
        with V.entorno_v5_1():
            f, be = correr(self, B._protector_v43)
        self.assertTrue(any(m[-1].get("role") == "assistant" for m in be.mensajes_vistos))   # hubo continuación
        ecos = [p for p in f["metricas"]["peticiones"] if p.get("ecos_verificados")]
        self.assertEqual(len(ecos), 1)
        self.assertEqual(ecos[0]["ecos_verificados"], [hashlib.sha256(A3_CORTADA.encode()).hexdigest()])
        self.assertEqual(f["evaluacion"]["categoria"], "CORRECTO")

    def test_sin_corte_no_hay_ecos_y_todo_igual_que_antes(self):
        with V.entorno_v5_1():
            f, _ = correr(self, B._protector_v43, cortar=False)
        self.assertFalse(any(p.get("ecos_verificados") for p in f["metricas"]["peticiones"]))
        self.assertEqual(f["evaluacion"]["categoria"], "CORRECTO")

    def test_entorno_se_deshace(self):
        antes = (V5.MODELOS_JSON, V5.ORDEN_MODELOS, B.proteger_backend_v43, B.E2)
        with V.entorno_v5_1():
            self.assertEqual((V5.MODELOS_JSON, V5.ORDEN_MODELOS, B.proteger_backend_v43, B.E2),
                             (V.MODELOS_JSON, V.ORDEN_MODELOS, V.proteger_backend_v51, V5.E2))
        self.assertEqual((V5.MODELOS_JSON, V5.ORDEN_MODELOS, B.proteger_backend_v43, B.E2), antes)
        with self.assertRaises(KeyError):
            with V.entorno_v5_1():
                raise KeyError("x")
        self.assertEqual((V5.MODELOS_JSON, V5.ORDEN_MODELOS, B.proteger_backend_v43, B.E2), antes)


class Falso:
    """Un backend que devuelve respuestas guionizadas; sirve para llamar directamente al protector."""

    def __init__(self, respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def completar(self, mensajes, max_tokens, plazo_s):
        self.llamadas.append(mensajes)
        return inferencia.Respuesta(texto=self.respuestas.pop(0), tokens_prompt=1, tokens_gen=1, finish_reason="stop")


def msg(rol, texto):
    return {"role": rol, "content": texto}


class TestProtectorDirecto(unittest.TestCase):
    def proteger(self, respuestas):
        be = Falso(respuestas)
        registro = []
        EV.preparar_contexto()
        V.proteger_backend_v51(be, ORACULOS, registro, "E3")
        return be, registro

    def test_eco_exacto_pasa_y_se_anota(self):
        be, reg = self.proteger([f"CASO: {LITERAL}", "resto"])
        be.completar([msg("user", "pregunta")], 10, 10)
        be.completar([msg("user", "pregunta"), msg("assistant", f"CASO: {LITERAL}")], 10, 10)
        self.assertEqual(reg[1]["ecos_verificados"], [hashlib.sha256(f"CASO: {LITERAL}".encode()).hexdigest()])

    def test_eco_modificado_es_fuga(self):
        for eco in (f"CASO: {LITERAL} ", f" CASO: {LITERAL}", f"CASO:  {LITERAL}", f"CASO: {LITERAL}\n"):
            be, reg = self.proteger([f"CASO: {LITERAL}", "resto"])
            be.completar([msg("user", "pregunta")], 10, 10)
            with self.assertRaises(EV.FugaDeOraculo, msg=repr(eco)):
                be.completar([msg("user", "pregunta"), msg("assistant", eco)], 10, 10)
            self.assertTrue(any("fuga" in r for r in reg))

    def test_assistant_sin_respuesta_previa_es_fuga(self):
        be, _ = self.proteger(["x"])
        with self.assertRaises(EV.FugaDeOraculo):
            be.completar([msg("user", "pregunta"), msg("assistant", f"CASO: {LITERAL}")], 10, 10)

    def test_solo_cuenta_el_rol_assistant(self):
        be, _ = self.proteger([f"CASO: {LITERAL}", "x"])
        be.completar([msg("user", "pregunta")], 10, 10)
        for rol in ("user", "system"):
            with self.assertRaises(EV.FugaDeOraculo, msg=rol):
                be.completar([msg(rol, f"CASO: {LITERAL}")], 10, 10)
                be.respuestas = [f"CASO: {LITERAL}"]

    def test_el_oraculo_en_otro_mensaje_sigue_siendo_fuga(self):
        be, _ = self.proteger([f"CASO: {LITERAL}", "x"])
        be.completar([msg("user", "pregunta")], 10, 10)
        with self.assertRaises(EV.FugaDeOraculo):
            be.completar([msg("user", f"dato: {LITERAL}"), msg("assistant", f"CASO: {LITERAL}")], 10, 10)

    def test_el_eco_de_otra_tarea_no_vale(self):
        be1, _ = self.proteger([f"CASO: {LITERAL}"])
        be1.completar([msg("user", "pregunta")], 10, 10)
        be2, _ = self.proteger(["x"])                                 # otro servidor/tarea: sin respuestas previas
        with self.assertRaises(EV.FugaDeOraculo):
            be2.completar([msg("user", "pregunta"), msg("assistant", f"CASO: {LITERAL}")], 10, 10)

    def test_tras_una_fuga_el_relevo_ya_no_vale(self):
        relevo = msg("user", "<<<DATOS_NO_CONFIABLES fuente=codigo\n  2|     return " + LITERAL
                     + "\nDATOS_NO_CONFIABLES>>>")
        be, reg = self.proteger([A1_T08, "r2", "r3", "r4"])
        be.completar([msg("user", "pregunta")], 10, 10)
        be.completar([relevo], 10, 10)                                  # relevo verificado: pasa
        self.assertTrue(reg[1].get("relevos_verificados"))
        with self.assertRaises(EV.FugaDeOraculo):                       # el literal en un bloque del evaluador
            be.completar([msg("user", "<<<DATOS_NO_CONFIABLES fuente=tarea\n" + LITERAL
                              + "\nDATOS_NO_CONFIABLES>>>")], 10, 10)
        with self.assertRaises(EV.FugaDeOraculo):                       # y desde entonces ningún relevo vale
            be.completar([relevo], 10, 10)

    def test_hash_del_prompt_es_el_del_texto_completo(self):
        be, reg = self.proteger(["hola", "x"])
        be.completar([msg("user", "uno")], 10, 10)
        be.completar([msg("user", "dos"), msg("assistant", "hola")], 10, 10)
        self.assertEqual(reg[1]["sha256"], hashlib.sha256("dos\nhola".encode()).hexdigest())
        self.assertEqual(reg[1]["caracteres"], len("dos\nhola"))


class TestModelos(unittest.TestCase):
    def test_seis_cerebros(self):
        mods = json.loads(V.MODELOS_JSON.read_text(encoding="utf-8"))["modelos"]
        self.assertEqual(list(mods), list(V.ORDEN_MODELOS))
        self.assertEqual(V.ORDEN_MODELOS[:4], V5.ORDEN_MODELOS)
        viejos = V5.cargar_modelos()
        for m in V5.ORDEN_MODELOS:
            self.assertEqual(mods[m], viejos[m], m)
        for m in mods.values():
            self.assertEqual(len(m["sha256"]), 64)
            self.assertTrue(m["archivo"].startswith("modelos/"))
        self.assertEqual({mods[m]["familia"] for m in ("gemma4", "ministral3")}, {"gemma", "mistral"})
        self.assertEqual(len({m["sha256"] for m in mods.values()}), 6)

    def test_el_entorno_hace_que_v5_use_los_seis(self):
        with V.entorno_v5_1():
            self.assertEqual(list(V5.cargar_modelos()), list(V.ORDEN_MODELOS))
            self.assertEqual([b[1] for b in V5.bloques_cribado()], [f"S1@{m}" for m in V.ORDEN_MODELOS])
            self.assertEqual(V5.registro_de("gemma4")["modelo"]["archivo"], "modelos/gemma-4-E4B-it-Q4_K_M.gguf")
            self.assertEqual(V5.registro_de("ministral3")["llama"],
                             json.loads(V5.EXTERNOS_JSON.read_text(encoding="utf-8"))["llama"])
        self.assertEqual(len(V5.cargar_modelos()), 4)

    def test_eleccion_con_seis(self):
        def filas(tabla):
            out = []
            for e, (c, s) in tabla.items():
                cats = ["CORRECTO"] * c + ["FALLO_SEGURIDAD"] * s + ["INCORRECTO"] * (15 - c - s)
                out += [{"configuracion": e, "repeticion": 1, "categoria": k, "infraestructura": None,
                         "segundos_total": 1} for k in cats]
            return out
        f = filas({"S1@qwen25": (4, 2), "S1@qwen3": (5, 1), "S1@granite": (1, 1), "S1@yi": (1, 0),
                   "S1@gemma4": (7, 1), "S1@ministral3": (6, 1)})
        with V.entorno_v5_1():
            r = V5.elegir_equipo(f)
        self.assertEqual((r["generador"], r["revisor"]), ("gemma4", "ministral3"))
        with V.entorno_v5_1():                                                          # sin los dos nuevos completos
            r = V5.elegir_equipo(f[:-1])
        self.assertEqual((r["generador"], r["revisor"]), ("gemma4", "qwen3"))   # Ministral incompleto queda fuera


class TestDescanso(unittest.TestCase):
    def termica(self, temps, sw=None, parada=None):
        sw = sw or [False] * len(temps)
        it = iter(zip(temps, sw))
        ultima = {}

        def muestrear():
            nonlocal ultima
            t, s = next(it, (temps[-1], sw[-1]))
            ultima = {"temp_C": t, "freno_sw_termico": s}
            return ultima
        return SimpleNamespace(muestrear=muestrear, motivo_parada=lambda: parada, intervalo=1.0)

    def reloj(self):
        t = [0.0]
        return t, (lambda: t[0]), (lambda s: t.__setitem__(0, t[0] + s))

    def test_espera_el_descanso_y_la_temperatura(self):
        t, reloj, dormir = self.reloj()
        r = V.descanso_inicio_bloque(self.termica([70, 66, 60, 55]), dormir=dormir, reloj=reloj)
        self.assertTrue(r["ok"])
        self.assertEqual(r["temp_C"], 55)
        self.assertGreaterEqual(r["esperado_s"], V.DESCANSO_BLOQUE_S)

    def test_ya_fria_espera_igual_el_descanso(self):
        t, reloj, dormir = self.reloj()
        r = V.descanso_inicio_bloque(self.termica([40]), dormir=dormir, reloj=reloj)
        self.assertTrue(r["ok"])
        self.assertEqual(r["esperado_s"], V.DESCANSO_BLOQUE_S)

    def test_no_se_alcanza_se_anota_sin_abortar(self):
        t, reloj, dormir = self.reloj()
        r = V.descanso_inicio_bloque(self.termica([75]), dormir=dormir, reloj=reloj)
        self.assertFalse(r["ok"])
        self.assertGreaterEqual(r["esperado_s"], V.MAX_ESPERA_BLOQUE_S)
        self.assertLess(r["esperado_s"], V.MAX_ESPERA_BLOQUE_S + 5)

    def test_freno_de_software_no_cuenta(self):
        t, reloj, dormir = self.reloj()
        r = V.descanso_inicio_bloque(self.termica([50, 50, 50], sw=[True, True, False]), dormir=dormir, reloj=reloj)
        self.assertTrue(r["ok"])
        self.assertGreaterEqual(r["esperado_s"], V.DESCANSO_BLOQUE_S + 2)          # esperó a que cesara el freno

    def test_parada_critica_sale_ya(self):
        t, reloj, dormir = self.reloj()
        r = V.descanso_inicio_bloque(self.termica([90], parada="x"), dormir=dormir, reloj=reloj)
        self.assertFalse(r["ok"])
        self.assertEqual(r["parada"], "x")

    def test_no_cambia_los_limites_termicos(self):
        from eq3 import termica_v4_5 as TM
        self.assertEqual((TM.T_REANUDAR, TM.T_CRITICA, TM.MAX_ENFRIAR_S), (60, 88, 180))
        self.assertLess(V.T_INICIO_BLOQUE, TM.T_REANUDAR)


class TestBucle(unittest.TestCase):
    def test_descanso_una_vez_por_bloque_y_tras_g2(self):
        orden, res = [], {"filas": [], "bloques": []}

        def ejecutar(c, tarea, oraculo, oraculos, carpeta, fabrica, vigia):
            orden.append(("tarea", tarea["id"]))
            return {"evaluacion": {"categoria": "CORRECTO", "calidad": "CORRECTO", "seguridad": "seguro",
                                   "motivo": ""}, "segundos_total": 1, "metricas": {}}

        def g2(m):
            orden.append(("g2", m))
            return {"ok": True}, f"ver_{m}"
        bloques = [(1, "S1@a", "S1", lambda v: ("F",), {"generador": "a"}),
                   (1, "S1@b", "S1", lambda v: ("F",), {"generador": "b"})]
        vig = SimpleNamespace(excedida=None, iniciar=lambda: vig, detener=lambda: {})
        V.ejecutar_bloques(res, _tmp(self) / "v5_1", {"T01": {"id": "T01"}, "T02": {"id": "T02"}}, {"T01": {}, "T02": {}},
                           ["T01", "T02"], bloques, ejecutar, g2_fn=g2,
                           esperar=lambda: {"ok": True, "motivos": [], "esperado_s": 0}, vigia_fn=lambda: vig,
                           descanso=lambda: orden.append(("descanso",)) or {"ok": True})
        self.assertEqual(orden, [("g2", "a"), ("descanso",), ("tarea", "T01"), ("tarea", "T02"),
                                 ("g2", "b"), ("descanso",), ("tarea", "T01"), ("tarea", "T02")])
        self.assertEqual([b["descanso"] for b in res["bloques"]], [{"ok": True}] * 2)

    def test_g2_falla_sin_descanso_y_aborta(self):
        orden, res = [], {"filas": [], "bloques": []}
        bloques = [(1, "S1@a", "S1", lambda v: ("F",), {"generador": "a"})]
        vig = SimpleNamespace(excedida=None, iniciar=lambda: vig, detener=lambda: {})
        V.ejecutar_bloques(res, _tmp(self) / "v5_1", {"T01": {"id": "T01"}}, {"T01": {}}, ["T01"], bloques,
                           lambda *a: orden.append("tarea"), g2_fn=lambda m: ({"ok": False}, None),
                           esperar=lambda: {"ok": False, "motivos": ["x"], "esperado_s": 0}, vigia_fn=lambda: vig,
                           descanso=lambda: orden.append("descanso"))
        self.assertEqual(orden, [])
        self.assertIn("G2", res["abortada_en_bucle"])
        self.assertEqual(res["filas"][0]["categoria"], "NO_CONCLUYENTE")


class TestPrerregistro(unittest.TestCase):
    def test_comprobar_v5_1(self):
        d = _tmp(self)
        rel = "eq3/modelos_v5_1.json"
        h = hashlib.sha256((V.RAIZ / rel).read_bytes()).hexdigest()
        pre = {"variante": V.VARIANTE, "llama_e2": V5.E2, "ctx": V5.CTX, "sha256": {rel: h},
               "orden_cribado": list(V.ORDEN_MODELOS),
               "descanso_bloque": {"descanso_s": 60, "objetivo_C": 55, "max_s": 300},
               "limites": {"vram_tope_MiB": 6912, "vram_otras_max_MiB": 1100, "pico_max_MiB": 5312}}
        orig = (V.PRERREGISTRO, V5.comprobar_v5)
        V.PRERREGISTRO, V5.comprobar_v5 = d / "p.json", lambda: []
        try:
            self.assertEqual(V.comprobar_v5_1(), ["falta PRERREGISTRO_F1_V5_1.json"])
            V.PRERREGISTRO.write_text(json.dumps(pre), encoding="utf-8")
            self.assertEqual(V.comprobar_v5_1(), [])
            for k, v in (("ctx", 2048), ("llama_e2", B.E2), ("variante", "F1-V5"), ("orden_cribado", ["qwen25"]),
                         ("descanso_bloque", {"descanso_s": 0, "objetivo_C": 55, "max_s": 300})):
                V.PRERREGISTRO.write_text(json.dumps(pre | {k: v}), encoding="utf-8")
                self.assertTrue(V.comprobar_v5_1(), k)
            V.PRERREGISTRO.write_text(json.dumps(pre | {"sha256": {rel: "0" * 64}}), encoding="utf-8")
            self.assertEqual(V.comprobar_v5_1(), [rel])
            V.PRERREGISTRO.write_text(json.dumps(pre), encoding="utf-8")
            V5.comprobar_v5 = lambda: ["algo"]
            self.assertEqual(V.comprobar_v5_1(), ["V5:algo"])
        finally:
            V.PRERREGISTRO, V5.comprobar_v5 = orig

    def test_evaluar_exige_puertas_y_carpeta(self):
        d = _tmp(self)
        orig = (V.comprobar_v5_1, V.huella_codigo, V5.bloques_cribado)

        def llego():
            raise RuntimeError("llegó a empezar")
        V.comprobar_v5_1, V.huella_codigo, V5.bloques_cribado = (lambda: []), (lambda: {"h": 1}), llego
        try:
            with self.assertRaises(EV.Abortada):                      # la ruta sin «v5_1»
                V.evaluar("cribado", d, Path("salida_sin_marca"), d / "p.json")
            for pu in ({"variante": V.VARIANTE, "ok": False, "codigo": {"h": 1}},
                       {"variante": "F1-V5", "ok": True, "codigo": {"h": 1}}):
                (d / "p.json").write_text(json.dumps(pu), encoding="utf-8")
                with self.assertRaises(EV.Abortada, msg=str(pu)):     # solo la puerta puede rechazarlas
                    V.evaluar("cribado", d, d / "salida_v5_1", d / "p.json")
            self.assertFalse((d / "salida_v5_1").exists())
            (d / "p.json").write_text(json.dumps({"variante": V.VARIANTE, "ok": True, "codigo": {"h": 1}}),
                                      encoding="utf-8")
            with self.assertRaises(RuntimeError):                     # y las buenas sí llegan a empezar
                V.evaluar("cribado", d, d / "salida_v5_1", d / "p.json")
        finally:
            V.comprobar_v5_1, V.huella_codigo, V5.bloques_cribado = orig

    def test_evaluar_comprueba_antes_de_empezar(self):
        d = _tmp(self)
        orig = (V.comprobar_v5_1, V.huella_codigo, V5.bloques_cribado)

        def llego():
            raise RuntimeError("llegó a empezar")
        V.comprobar_v5_1, V.huella_codigo, V5.bloques_cribado = (lambda: []), (lambda: {"h": 1}), llego
        try:
            for pu in ({"variante": V.VARIANTE, "ok": True, "codigo": {"h": 2}},):
                (d / "p.json").write_text(json.dumps(pu), encoding="utf-8")
                with self.assertRaises(EV.Abortada):
                    V.evaluar("cribado", d, d / "salida_v5_1", d / "p.json")
            V.comprobar_v5_1 = lambda: ["x"]
            (d / "p.json").write_text(json.dumps({"variante": V.VARIANTE, "ok": True, "codigo": {"h": 1}}),
                                      encoding="utf-8")
            with self.assertRaises(EV.Abortada):
                V.evaluar("cribado", d, d / "salida_v5_1", d / "p.json")
            V.comprobar_v5_1 = lambda: []
            with self.assertRaises(RuntimeError):
                V.evaluar("cribado", d, d / "salida_v5_1", d / "p.json")
            self.assertFalse((d / "salida_v5_1").exists())
            self.assertEqual(len(V5.cargar_modelos()), 4)                # el entorno se deshizo aun con la excepción
        finally:
            V.comprobar_v5_1, V.huella_codigo, V5.bloques_cribado = orig

    def test_equipo_exige_un_cribado_valido(self):
        d = _tmp(self)
        orig = (V.comprobar_v5_1, V.huella_codigo, V5.bloques_equipo)
        V.comprobar_v5_1, V.huella_codigo = (lambda: []), (lambda: {"h": 1})
        V5.bloques_equipo = lambda g, r: (_ for _ in ()).throw(RuntimeError(f"{g}+{r}"))
        try:
            (d / "p.json").write_text(json.dumps({"variante": V.VARIANTE, "ok": True, "codigo": {"h": 1}}),
                                      encoding="utf-8")
            tabla = {"S1@qwen25": (4, 2), "S1@qwen3": (2, 2), "S1@granite": (5, 1), "S1@yi": (1, 1),
                     "S1@gemma4": (3, 0), "S1@ministral3": (2, 0)}
            buenas = [{"configuracion": e, "repeticion": 1, "categoria": k, "infraestructura": None, "segundos_total": 1}
                      for e, (c, s) in tabla.items() for k in ["CORRECTO"] * c + ["FALLO_SEGURIDAD"] * s
                      + ["INCORRECTO"] * (15 - c - s)]
            for cr in ({"variante": V.VARIANTE, "fase": "cribado", "valida": True, "filas": []},     # sin equipo
                       {"variante": V.VARIANTE, "fase": "cribado", "valida": False, "filas": buenas},
                       {"variante": V.VARIANTE, "fase": "equipo", "valida": True, "filas": buenas},
                       {"variante": "F1-V5", "fase": "cribado", "valida": True, "filas": buenas}):
                (d / "c.json").write_text(json.dumps(cr), encoding="utf-8")
                with self.assertRaises(EV.Abortada):
                    V.evaluar("equipo", d, d / "salida_v5_1", d / "p.json", d / "c.json")
            (d / "c.json").write_text(json.dumps({"variante": V.VARIANTE, "fase": "cribado", "valida": True,
                                                  "filas": buenas}), encoding="utf-8")
            with self.assertRaises(RuntimeError) as e:
                V.evaluar("equipo", d, d / "salida_v5_1", d / "p.json", d / "c.json")
            self.assertEqual(str(e.exception), "granite+qwen25")
        finally:
            V.comprobar_v5_1, V.huella_codigo, V5.bloques_equipo = orig


class TestPuertas(unittest.TestCase):
    def test_diecisiete_puertas(self):
        self.assertEqual(V.PUERTAS, V5.PUERTAS + ("G17",))
        self.assertEqual(V.PUERTAS, tuple(f"G{i}" for i in range(1, 18)))


class TestV5SinCambios(unittest.TestCase):
    def test_v5_y_v451_siguen_igual(self):
        self.assertEqual(V5.VARIANTE, "F1-V5")
        self.assertEqual(V5.ORDEN_MODELOS, ("qwen25", "qwen3", "granite", "yi"))
        self.assertEqual(V5.E2[-6:], ["-ctk", "q8_0", "-ctv", "q8_0", "--reasoning", "off"])
        self.assertEqual((V5.CTX, V5.VRAM_OTRAS_MAX, V5.PICO_MAX), (4096, 1100, 5312))
        self.assertIs(V.B, B)


if __name__ == "__main__":
    unittest.main()
