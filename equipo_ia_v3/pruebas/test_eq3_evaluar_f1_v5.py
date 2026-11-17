"""Pruebas de V3.1 F1-V5 (`eq3/evaluar_f1_v5.py`): E2 de V5, el equipo de dos cerebros (`BackendMixto`), las reglas
prerregistradas del cribado y del equipo, y el bucle por bloques. Sin GPU ni modelo: los backends son simulados y nada
generado se ejecuta.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_evaluar_f1_v5.py -v
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import comun  # noqa: F401
import aux_procedencia_v4_3 as A
from eq2 import config, inferencia
from eq2 import funcion_supervisada as FS
from eq3 import evaluar_f1 as EV
from eq3 import evaluar_f1_v5 as V
from eq3 import evaluar_f1_vram_exp_v4_5_1 as B

TAREAS, ORACULOS = EV.E.cargar()

LOG_OK = """load_tensors: offloaded 37/37 layers to GPU
llama_context: n_ctx                 = 4096
llama_context: n_ubatch              = 128
llama_context: flash_attn            = enabled
llama_kv_cache: size =  306.00 MiB (  4096 cells,  36 layers,  1/1 seqs), K (q8_0):  153.00 MiB, V (q8_0):  153.00 MiB
srv          init: init: chat template, thinking = 0
"""


def _tmp(caso) -> Path:
    d = Path(tempfile.mkdtemp(prefix="f1t_"))
    caso.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
    return d


class Falso:
    """Un backend simulado con nombre: guarda sus peticiones y su ciclo de vida en `diario` (compartido)."""

    def __init__(self, nombre, diario, limpio=True, ok=True):
        self.nombre, self.diario, self.limpio, self.ok = nombre, diario, limpio, ok
        self.estado, self.detencion, self.peticiones, self.carga_s, self.mon = "nuevo", None, [], 1.5, None
        self.srv = SimpleNamespace(proc=None, pid=lambda: None)
        self.soporta_continuacion, self.comprobaciones, self.ctx = False, {"ok": True}, None

    def iniciar(self, ctx=None):
        self.ctx, self.estado = ctx, "listo"
        self.diario.append(("iniciar", self.nombre, (ctx or {}).get("run_id")))

    def completar(self, mensajes, max_tokens, plazo_s):
        self.diario.append(("completar", self.nombre))
        self.peticiones.append({"status": 200, "de": self.nombre})
        return inferencia.Respuesta(texto="FIN", tokens_prompt=1, tokens_gen=1, finish_reason="stop")

    def supervisar(self):
        return None

    def detener(self):
        self.estado = "detenido"
        self.diario.append(("detener", self.nombre))
        self.detencion = {"ok": self.ok, "limpio": self.limpio, "problemas": [] if self.limpio else ["x"]}
        return self.detencion

    def informe(self):
        return {"nombre": self.nombre}


class Lab:
    def __init__(self):
        self.dirs = []

    def crear_dir(self, *partes):
        self.dirs.append(partes)


def mensajes(paso):
    return [{"role": "system", "content": "Eres X. " + FS.INSTR_FS[paso]}, {"role": "user", "content": "tarea"}]


def mixto(diario, procesos=lambda: [], **kw):
    return V.BackendMixto({"generador": lambda: Falso("gen", diario, **kw.get("gen", {})),
                           "revisor": lambda: Falso("rev", diario, **kw.get("rev", {}))}, procesos=procesos)


class TestE2(unittest.TestCase):
    def test_e2_es_el_de_v4_5_1_mas_cache_y_sin_thinking(self):
        self.assertEqual(V.E2[:len(B.E2)], B.E2)
        self.assertEqual(V.E2[len(B.E2):], ["-ctk", "q8_0", "-ctv", "q8_0", "--reasoning", "off"])
        self.assertEqual((V.CTX, V.VRAM_OTRAS_MAX, V.PICO_MAX, V.VRAM_TOPE), (4096, 1100, 5312, 6912))

    def test_configuracion_efectiva(self):
        self.assertTrue(V.configuracion_efectiva(LOG_OK)["ok"])
        for viejo, nuevo in (("= 4096\n", "= 2048\n"), ("K (q8_0)", "K (f16)"), ("V (q8_0)", "V (f16)"),
                             ("thinking = 0", "thinking = 1"), ("37/37", "30/37"), ("n_ubatch              = 128",
                                                                                  "n_ubatch              = 512")):
            self.assertFalse(V.configuracion_efectiva(LOG_OK.replace(viejo, nuevo))["ok"], nuevo)
        for falta in ("thinking", "K (q8_0)", "n_ctx  "):
            self.assertFalse(V.configuracion_efectiva("\n".join(l for l in LOG_OK.splitlines() if falta not in l))["ok"])
        self.assertFalse(V.configuracion_efectiva(LOG_OK + "fitting params\n")["ok"])

    def test_comprobar_logs_exige_todos(self):
        d = _tmp(self)
        (d / "a").mkdir()
        (d / "b").mkdir()
        (d / "a" / "server.log").write_text(LOG_OK, encoding="utf-8")
        self.assertTrue(V.comprobar_logs(d)["ok"])
        (d / "b" / "server.log").write_text(LOG_OK.replace("K (q8_0)", "K (f16)"), encoding="utf-8")
        r = V.comprobar_logs(d)
        self.assertEqual(r["logs"], 2)
        self.assertFalse(r["ok"])
        self.assertFalse(V.comprobar_logs(_tmp(self))["ok"])          # sin logs no hay E2

    def test_entorno_v5_se_deshace(self):
        antes = (B.E2, B.comprobar_logs)
        with V.entorno_v5():
            self.assertEqual((B.E2, B.comprobar_logs, config.CTX), (V.E2, V.comprobar_logs, 4096))
            self.assertEqual(config.PERFIL_CONTEXTO, "referencia")      # presupuestos de 2048: los topes de F1
            self.assertEqual(FS.TOKENS_FS[2048 if config.CTX >= 2048 else 1024]["fs_revisar"], 260)
        self.assertEqual((B.E2, B.comprobar_logs), antes)
        with self.assertRaises(KeyError):
            with V.entorno_v5():
                raise KeyError("x")
        self.assertEqual((B.E2, B.comprobar_logs), antes)

    def test_registro_de_cambia_solo_el_modelo(self):
        base = json.loads(V.EXTERNOS_JSON.read_text(encoding="utf-8"))
        mods = V.cargar_modelos()
        self.assertEqual(list(mods), list(V.ORDEN_MODELOS))
        for m in V.ORDEN_MODELOS:
            r = V.registro_de(m)
            self.assertEqual(r["llama"], base["llama"])
            self.assertEqual(r["modelo"]["sha256"], mods[m]["sha256"])
            self.assertEqual(len(mods[m]["sha256"]), 64)
        self.assertEqual(V.registro_de("qwen25")["modelo"]["sha256"], base["modelo"]["sha256"])


class TestPasoDe(unittest.TestCase):
    def test_prompts_reales_de_v2f1(self):
        """Con el armado REAL de prompts de V2-F.1: cada paso se reconoce y coincide con «Eres An»."""
        EV.preparar_contexto()
        vistos = []

        class Captura(A.Guion):
            def completar(s, m, max_tokens, plazo_s):
                vistos.append(m)
                return super().completar(m, max_tokens, plazo_s)
        ag = FS.AgentesFuncionLLM(Captura())
        t = TAREAS["T10"]["instrucciones"]
        ag.generar_fs(t, "orden", "casos")
        ag.revisar_fs(t, "def f(): pass", "EV1")
        ag.casos_fs(t, "def f(): pass", "EV1")
        ag.corregir_fs(t, "def f(): pass", "P1")
        pasos = [V.paso_de(m) for m in vistos]
        self.assertEqual(pasos, ["fs_generar", "fs_revisar", "fs_casos", "fs_corregir"])
        for p, m in zip(pasos, vistos):
            self.assertIn(f"Eres {FS.AGENTE_FS[p]}", m[0]["content"])

    def test_desconocido_o_ambiguo(self):
        self.assertIsNone(V.paso_de([{"role": "user", "content": "hola"}]))
        doble = FS.INSTR_FS["fs_generar"] + FS.INSTR_FS["fs_revisar"]
        self.assertIsNone(V.paso_de([{"role": "system", "content": doble}]))
        self.assertIsNone(V.paso_de([]))


class TestBackendMixto(unittest.TestCase):
    def test_ruta_por_agente_y_un_servidor_a_la_vez(self):
        d, lab = [], Lab()
        be = mixto(d)
        self.assertEqual(be.estado, "nuevo")
        be.iniciar({"lab": lab, "run_id": "E001"})
        for p in ("fs_generar", "fs_revisar", "fs_casos", "fs_corregir", "fs_revisar"):
            be.completar(mensajes(p), 10, 10)
        self.assertEqual([x[1] for x in d if x[0] == "completar"], ["gen", "rev", "rev", "gen", "rev"])
        vivos = 0
        for x in d:                                               # nunca dos iniciados sin detener entre medias
            vivos += {"iniciar": 1, "detener": -1}.get(x[0], 0)
            self.assertLessEqual(vivos, 1)
        self.assertEqual([x[2] for x in d if x[0] == "iniciar"], ["E001", "E001_c1", "E001_c2", "E001_c3"])
        self.assertEqual(lab.dirs, [("runs", "E001_c1"), ("runs", "E001_c2"), ("runs", "E001_c3")])
        self.assertEqual(len(be.cambios), 3)
        self.assertEqual(len(be.peticiones), 5)
        self.assertEqual(be.carga_s, 6.0)
        det = be.detener()
        self.assertTrue(det["ok"] and det["limpio"])
        self.assertEqual(be.estado, "detenido")
        self.assertIs(be.detener(), det)
        self.assertEqual(d[-1], ("detener", "rev"))

    def test_s1_no_cambia_nunca(self):
        d = []
        be = mixto(d)
        be.iniciar({"lab": Lab(), "run_id": "R"})
        be.completar(mensajes("fs_generar"), 10, 10)
        self.assertEqual(be.cambios, [])
        self.assertEqual(len(be.usados), 1)

    def test_llama_vivo_tras_parar_aborta(self):
        for procesos in (lambda: [{"pid": 7}], lambda: None):
            d = []
            be = mixto(d, procesos=procesos)
            be.iniciar({"lab": Lab(), "run_id": "R"})
            with self.assertRaises(inferencia.ErrorInferencia) as e:
                be.completar(mensajes("fs_revisar"), 10, 10)
            self.assertTrue(e.exception.fatal)
            self.assertIn("cambio_de_cerebro_fallido", e.exception.motivo)
            self.assertFalse(any(x == ("iniciar", "rev", "R_c1") for x in d))

    def test_cierre_sucio_aborta(self):
        for kw in ({"gen": {"limpio": False}}, {"gen": {"ok": False}}):
            be = mixto([], **kw)
            be.iniciar({"lab": Lab(), "run_id": "R"})
            with self.assertRaises(inferencia.ErrorInferencia):
                be.completar(mensajes("fs_casos"), 10, 10)
            self.assertFalse(be.detener()["ok"] and be.detener()["limpio"])

    def test_paso_desconocido_va_al_generador(self):
        d = []
        be = mixto(d)
        be.iniciar({"lab": Lab(), "run_id": "R"})
        be.completar(mensajes("fs_revisar"), 10, 10)
        be.completar([{"role": "user", "content": "otra cosa"}], 10, 10)
        self.assertEqual(be.rol_actual, "generador")
        self.assertEqual(be.pasos_desconocidos, 1)
        self.assertEqual(be.detener()["pasos_desconocidos"], 1)

    def test_iniciar_dos_veces(self):
        be = mixto([])
        be.iniciar({"lab": Lab(), "run_id": "R"})
        with self.assertRaises(inferencia.ErrorInferencia):
            be.iniciar({"lab": Lab(), "run_id": "R"})

    def test_detener_sin_iniciar(self):
        self.assertTrue(mixto([]).detener()["ok"])

    def test_cierre_final_sucio_cuenta(self):
        be = mixto([], rev={"limpio": False})
        be.iniciar({"lab": Lab(), "run_id": "R"})
        be.completar(mensajes("fs_revisar"), 10, 10)                 # el generador cerró limpio
        d = be.detener()
        self.assertFalse(d["limpio"])
        self.assertTrue(d["ok"])
        self.assertEqual(d["problemas"], ["x"])


class TestG2(unittest.TestCase):
    def test_vram_ajena_y_externos(self):
        orig = (V.servidor_pc.verificar_externos, V.servidor_pc.vram_mib)
        vistos = []
        try:
            V.servidor_pc.verificar_externos = lambda c, registro=None: vistos.append(registro) or {"ok": True}
            for usada, ok in ((1100, True), (1101, False)):
                V.servidor_pc.vram_mib = lambda u=usada: {"usada": u}
                self.assertEqual(V.g2(Path("."), "yi")[0]["ok"], ok, usada)
            self.assertEqual(vistos[-1]["modelo"]["sha256"], V.cargar_modelos()["yi"]["sha256"])
            V.servidor_pc.vram_mib = lambda: None
            self.assertFalse(V.g2(Path("."), "yi")[0]["ok"])
            V.servidor_pc.vram_mib = lambda: {"usada": 10}
            V.servidor_pc.verificar_externos = lambda c, registro=None: {"ok": False, "problemas": ["sha"]}
            self.assertFalse(V.g2(Path("."), "yi")[0]["ok"])
        finally:
            V.servidor_pc.verificar_externos, V.servidor_pc.vram_mib = orig


class TestFlujoRealE3(unittest.TestCase):
    """REAL: `EV.ejecutar_tarea` (E3 de V2-F.1) con el protector de V4.3. SIMULADO: los dos cerebros (guiones)."""

    def test_e3_con_dos_cerebros(self):
        EV.preparar_contexto()
        gen, rev = A.Guion(), A.Guion()
        be = V.BackendMixto({"generador": lambda: gen, "revisor": lambda: rev}, procesos=lambda: [])
        vig = EV.Vigia(medir=lambda: None, intervalo=0.05).iniciar()
        try:
            with B._protector_v43("E3"):
                f = EV.ejecutar_tarea("E3", TAREAS["T10"], ORACULOS["T10"], ORACULOS, _tmp(self) / "E3", lambda: be,
                                      vig)
        finally:
            vig.detener()
        self.assertEqual(f["evaluacion"]["categoria"], "CORRECTO")
        self.assertTrue(gen.prompts and rev.prompts)
        self.assertTrue(all("Eres A1" in p for p in gen.prompts))
        self.assertTrue(all("Eres A2" in p or "Eres A3" in p for p in rev.prompts))
        self.assertEqual(be.pasos_desconocidos, 0)
        self.assertEqual(f["metricas"]["llamadas"], len(gen.prompts) + len(rev.prompts))


def filas(tabla, rep=1):
    """tabla = {etiqueta: (correctas, fallos_seguridad, n)}"""
    out = []
    for e, (c, s, n) in tabla.items():
        cats = ["CORRECTO"] * c + ["FALLO_SEGURIDAD"] * s + ["INCORRECTO"] * (n - c - s)
        out += [{"configuracion": e, "repeticion": rep, "categoria": k, "infraestructura": None,
                 "segundos_total": 1} for k in cats]
    return out


class TestReglas(unittest.TestCase):
    MOD = {"qwen25": {"familia": "qwen"}, "qwen3": {"familia": "qwen"}, "granite": {"familia": "granite"},
           "yi": {"familia": "yi"}}

    def elegir(self, tabla):
        return V.elegir_equipo(filas(tabla), self.MOD, n_tareas=15)

    def test_generador_y_revisor_de_otra_familia(self):
        r = self.elegir({"S1@qwen25": (4, 2, 15), "S1@qwen3": (6, 2, 15), "S1@granite": (3, 1, 15),
                         "S1@yi": (5, 3, 15)})
        self.assertEqual((r["generador"], r["revisor"]), ("qwen3", "yi"))       # qwen25 es de la misma familia

    def test_desempates(self):
        r = self.elegir({"S1@qwen25": (4, 2, 15), "S1@qwen3": (4, 1, 15), "S1@granite": (4, 1, 15), "S1@yi": (4, 1, 15)})
        self.assertEqual((r["generador"], r["revisor"]), ("qwen3", "granite"))  # menos fallos; luego, orden
        r = self.elegir({"S1@qwen25": (4, 2, 15), "S1@qwen3": (4, 2, 15), "S1@granite": (4, 2, 15), "S1@yi": (4, 2, 15)})
        self.assertEqual((r["generador"], r["revisor"]), ("qwen25", "granite"))

    def test_incompletos_fuera(self):
        r = self.elegir({"S1@qwen25": (4, 2, 15), "S1@qwen3": (9, 0, 14), "S1@granite": (3, 1, 15), "S1@yi": (5, 3, 15)})
        self.assertEqual(r["generador"], "yi")
        self.assertEqual(r["revisor"], "qwen25")
        f = filas({"S1@qwen25": (4, 2, 15), "S1@granite": (9, 0, 15)})
        f[-1]["infraestructura"] = "x"
        self.assertEqual(V.elegir_equipo(f, self.MOD, n_tareas=15)["generador"], "qwen25")
        self.assertFalse(V.elegir_equipo(filas({"S1@qwen25": (4, 2, 15)}), self.MOD, n_tareas=15)["ok"])
        self.assertFalse(V.elegir_equipo([], self.MOD, n_tareas=15)["ok"])

    def test_supera(self):
        f = filas({"a": (7, 1, 15), "b": (4, 1, 15)}, 1) + filas({"a": (7, 1, 15), "b": (4, 1, 15)}, 2)
        self.assertTrue(V.supera(f, "a", "b")["supera"])
        f2 = filas({"a": (7, 1, 15), "b": (4, 1, 15)}, 1) + filas({"a": (6, 1, 15), "b": (4, 1, 15)}, 2)
        self.assertFalse(V.supera(f2, "a", "b")["supera"])                      # 2 < 3 en la repetición 2
        f3 = filas({"a": (7, 2, 15), "b": (4, 1, 15)}, 1) + filas({"a": (7, 2, 15), "b": (4, 1, 15)}, 2)
        self.assertFalse(V.supera(f3, "a", "b")["supera"])                      # más fallos de seguridad
        self.assertTrue(V.supera(filas({"a": (7, 1, 15), "b": (4, 1, 15)}), "a", "b", reps=(1,))["supera"])


class TestBloques(unittest.TestCase):
    def test_cribado(self):
        b = V.bloques_cribado()
        self.assertEqual([x[1] for x in b], ["S1@qwen25", "S1@qwen3", "S1@granite", "S1@yi"])
        self.assertTrue(all(x[0] == 1 and x[2] == "S1" for x in b))

    def test_equipo_contrabalanceado(self):
        b = V.bloques_equipo("qwen3", "yi")
        self.assertEqual([(x[0], x[1], x[2]) for x in b],
                         [(1, "S1@qwen3", "S1"), (1, "E3@qwen3", "E3"), (1, "E3@qwen3+yi", "E3"),
                          (2, "E3@qwen3+yi", "E3"), (2, "E3@qwen3", "E3"), (2, "S1@qwen3", "S1")])
        self.assertEqual(b[2][4], {"generador": "qwen3", "revisor": "yi"})
        orig = B.fabrica_e2
        B.fabrica_e2 = lambda ver: ("uno", ver)
        try:
            self.assertEqual(b[0][3]({"generador": "VG"}), ("uno", "VG"))
            self.assertIsInstance(b[2][3]({"generador": "VG", "revisor": "VR"})(), V.BackendMixto)
        finally:
            B.fabrica_e2 = orig

    def correr(self, g2_ok=lambda m: True):
        llamadas, res = [], {"filas": [], "bloques": []}

        def ejecutar(c, tarea, oraculo, oraculos, carpeta, fabrica, vigia):
            llamadas.append((c, tarea["id"], fabrica))
            return {"evaluacion": {"categoria": "CORRECTO", "calidad": "CORRECTO", "seguridad": "seguro",
                                   "motivo": ""}, "segundos_total": 1, "metricas": {}}
        bloques = [(1, "S1@qwen25", "S1", lambda vers: ("F", vers["generador"]), {"generador": "qwen25"}),
                   (1, "E3@qwen25+yi", "E3", lambda vers: ("F", vers["generador"], vers["revisor"]),
                    {"generador": "qwen25", "revisor": "yi"})]
        vig = SimpleNamespace(excedida=None, iniciar=lambda: vig, detener=lambda: {})
        V.ejecutar_bloques(res, _tmp(self) / "v5", {"T01": {"id": "T01"}, "T02": {"id": "T02"}}, {"T01": {}, "T02": {}},
                           ["T01", "T02"], bloques, ejecutar,
                           g2_fn=lambda m: ({"ok": g2_ok(m)}, f"ver_{m}"),
                           esperar=lambda: {"ok": True, "motivos": [], "esperado_s": 0}, vigia_fn=lambda: vig)
        return llamadas, res

    def test_bucle(self):
        llamadas, res = self.correr()
        self.assertEqual([(c, t) for c, t, _ in llamadas], [("S1", "T01"), ("S1", "T02"), ("E3", "T01"), ("E3", "T02")])
        self.assertEqual(llamadas[2][2], ("F", "ver_qwen25", "ver_yi"))
        self.assertEqual([f["configuracion"] for f in res["filas"]], ["S1@qwen25"] * 2 + ["E3@qwen25+yi"] * 2)
        self.assertEqual(res["filas"][2]["modelos"], {"generador": "qwen25", "revisor": "yi"})
        self.assertIsNone(res["abortada_en_bucle"])

    def test_g2_falla_aborta_lo_que_queda(self):
        llamadas, res = self.correr(g2_ok=lambda m: m != "yi")
        self.assertEqual(len(llamadas), 2)
        self.assertIn("yi", res["abortada_en_bucle"])
        self.assertEqual([f["categoria"] for f in res["filas"][2:]], ["NO_CONCLUYENTE"] * 2)


class TestPrerregistro(unittest.TestCase):
    def test_comprobar_v5(self):
        d = _tmp(self)
        rel = "eq3/modelos_v5.json"
        h = __import__("hashlib").sha256((V.RAIZ / rel).read_bytes()).hexdigest()
        pre = {"variante": V.VARIANTE, "llama_e2": V.E2, "ctx": V.CTX, "sha256": {rel: h},
               "limites": {"vram_tope_MiB": 6912, "vram_otras_max_MiB": 1100, "pico_max_MiB": 5312}}
        orig = (V.PRERREGISTRO, B.comprobar_v4)
        V.PRERREGISTRO, B.comprobar_v4 = d / "p.json", lambda: []
        try:
            self.assertEqual(V.comprobar_v5(), ["falta PRERREGISTRO_F1_V5.json"])
            V.PRERREGISTRO.write_text(json.dumps(pre), encoding="utf-8")
            self.assertEqual(V.comprobar_v5(), [])
            for k, v in (("ctx", 2048), ("llama_e2", B.E2), ("variante", "F1-V4")):
                V.PRERREGISTRO.write_text(json.dumps(pre | {k: v}), encoding="utf-8")
                self.assertTrue(V.comprobar_v5(), k)
            V.PRERREGISTRO.write_text(json.dumps(pre | {"sha256": {rel: "0" * 64}}), encoding="utf-8")
            self.assertEqual(V.comprobar_v5(), [rel])
            V.PRERREGISTRO.write_text(json.dumps(pre), encoding="utf-8")
            B.comprobar_v4 = lambda: ["algo"]
            self.assertEqual(V.comprobar_v5(), ["V4.5.1:algo"])
        finally:
            V.PRERREGISTRO, B.comprobar_v4 = orig

    def test_evaluar_exige_puertas_y_carpeta(self):
        d = _tmp(self)
        with self.assertRaises(EV.Abortada):
            V.evaluar("cribado", d, Path("salida_sin_marca"), d / "p.json")      # sin «v5» en la ruta
        (d / "p.json").write_text(json.dumps({"variante": V.VARIANTE, "ok": False}), encoding="utf-8")
        with self.assertRaises(EV.Abortada):
            V.evaluar("cribado", d, d / "salida_v5", d / "p.json")
        (d / "p.json").write_text(json.dumps({"variante": "F1-VRAM-EXP-V4.5.1", "ok": True}), encoding="utf-8")
        with self.assertRaises(EV.Abortada):
            V.evaluar("cribado", d, d / "salida_v5", d / "p.json")
        self.assertFalse((d / "salida_v5").exists())

    def test_evaluar_comprueba_antes_de_empezar(self):
        """Con prerregistro y código «intactos» (simulados), solo unas puertas válidas de ESTE código dejan pasar; si
        algo pasa de más, `bloques_cribado` (simulado) lo delata antes de crear nada."""
        d = _tmp(self)
        orig = (V.comprobar_v5, V.huella_codigo, V.bloques_cribado)

        def llego():
            raise RuntimeError("llegó a empezar")
        V.comprobar_v5, V.huella_codigo, V.bloques_cribado = (lambda: []), (lambda: {"h": 1}), llego
        try:
            for pu in ({"variante": V.VARIANTE, "ok": False, "codigo": {"h": 1}},
                       {"variante": "F1-VRAM-EXP-V4.5.1", "ok": True, "codigo": {"h": 1}},
                       {"variante": V.VARIANTE, "ok": True, "codigo": {"h": 2}}):
                (d / "p.json").write_text(json.dumps(pu), encoding="utf-8")
                with self.assertRaises(EV.Abortada, msg=str(pu)):
                    V.evaluar("cribado", d, d / "salida_v5", d / "p.json")
            V.comprobar_v5 = lambda: ["x"]
            (d / "p.json").write_text(json.dumps({"variante": V.VARIANTE, "ok": True, "codigo": {"h": 1}}),
                                      encoding="utf-8")
            with self.assertRaises(EV.Abortada):
                V.evaluar("cribado", d, d / "salida_v5", d / "p.json")
            V.comprobar_v5 = lambda: []
            with self.assertRaises(RuntimeError):                    # todo en orden: sí llega
                V.evaluar("cribado", d, d / "salida_v5", d / "p.json")
            self.assertFalse((d / "salida_v5").exists())
        finally:
            V.comprobar_v5, V.huella_codigo, V.bloques_cribado = orig

    def test_equipo_exige_un_cribado_valido(self):
        d = _tmp(self)
        orig = (V.comprobar_v5, V.huella_codigo, V.bloques_equipo)
        V.comprobar_v5, V.huella_codigo = (lambda: []), (lambda: {"h": 1})
        V.bloques_equipo = lambda g, r: (_ for _ in ()).throw(RuntimeError(f"{g}+{r}"))
        try:
            (d / "p.json").write_text(json.dumps({"variante": V.VARIANTE, "ok": True, "codigo": {"h": 1}}),
                                      encoding="utf-8")
            buenas = filas({"S1@qwen25": (4, 2, 15), "S1@qwen3": (2, 2, 15), "S1@granite": (5, 1, 15),
                            "S1@yi": (1, 1, 15)})
            for cr in ({"variante": V.VARIANTE, "fase": "cribado", "valida": False, "filas": buenas},
                       {"variante": V.VARIANTE, "fase": "equipo", "valida": True, "filas": buenas},
                       {"variante": V.VARIANTE, "fase": "cribado", "valida": True, "filas": []}):
                (d / "c.json").write_text(json.dumps(cr), encoding="utf-8")
                with self.assertRaises(EV.Abortada):
                    V.evaluar("equipo", d, d / "salida_v5", d / "p.json", d / "c.json")
            (d / "c.json").write_text(json.dumps({"variante": V.VARIANTE, "fase": "cribado", "valida": True,
                                                  "filas": buenas}), encoding="utf-8")
            with self.assertRaises(RuntimeError) as e:
                V.evaluar("equipo", d, d / "salida_v5", d / "p.json", d / "c.json")
            self.assertEqual(str(e.exception), "granite+qwen25")
        finally:
            V.comprobar_v5, V.huella_codigo, V.bloques_equipo = orig


if __name__ == "__main__":
    unittest.main()
