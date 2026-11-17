"""Pruebas de la arenilla (granos), del punto de reanudación y de la puntuación del diagnóstico de partidas (lab_saves).
Sin GPU: el cerebro es un doble que devuelve respuestas fijas."""
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_saves"))
import arenilla as A  # noqa: E402
import crear_copias_rimworld as CRW  # noqa: E402
import diagnostico_lab as D  # noqa: E402
import traductor_rimworld as TR  # noqa: E402
from test_lab_saves_pz import partida as partida_pz  # noqa: E402
from test_lab_saves_rimworld import partida as partida_rw  # noqa: E402

FINAL_SANA = "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: no hacer nada"


class Granos(unittest.TestCase):
    def test_empaquetar_respeta_el_limite_y_no_pierde_lineas(self):
        lineas = [f"línea {i} " + "x" * (i * 7 % 90) for i in range(60)]
        granos = A.empaquetar(lineas, 300)
        self.assertTrue(all(len(g) <= 300 for g in granos))
        self.assertEqual("\n".join(granos).split("\n"), lineas)

    def test_linea_larga_se_corta_con_marca(self):
        granos = A.empaquetar(["a" * 5000, "b"], 300)
        self.assertTrue(all(len(g) <= 300 for g in granos))
        self.assertIn("[cortado]", granos[0])

    def test_pasada_por_bloques_cuenta_igual_que_el_traductor(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "p.rws"
            p.write_bytes(partida_rw())
            inf = TR.traducir(p)
            for bloque in (1024, 5000, 1 << 20):
                texto = "\n".join(A.lineas_rw(p, "x", bloque))
                self.assertIn(f"mapas {inf['maps']}, cosas {inf['things']}, peones {inf['pawns']}", texto)
                self.assertIn(f"IDs de cosas repetidos: {inf['ids_repetidos']}", texto)
                self.assertIn("termina en </savegame>: sí", texto)

    def test_el_error_xml_cae_en_el_bloque_correcto_y_los_siguientes_no_se_leen(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "p.rws"
            nuevo, _, _ = CRW.d_cierre_borrado(partida_rw(), random.Random(1))
            p.write_bytes(nuevo)
            bloque = 4096
            nb = -(-len(nuevo) // bloque)
            filas = [l for l in A.lineas_rw(p, "x", bloque) if l.startswith("bloque ")]
            self.assertEqual(len(filas), nb)
            con_error = [n for n, l in enumerate(filas) if "XML ERROR" in l]
            self.assertEqual(len(con_error), 1)
            esperado = TR.traducir(p)["error_en_fraccion"]
            self.assertAlmostEqual(con_error[0] / nb, esperado, delta=1.5 / nb + 0.02)
            self.assertTrue(all("sin leer" in l for l in filas[con_error[0] + 1:]))
            self.assertTrue(all("correcto" in l for l in filas[:con_error[0]]))

    def test_bytes_nulos_por_bloque(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "p.rws"
            nuevo, _, _ = CRW.d_cola_a_ceros(partida_rw(), random.Random(1))
            p.write_bytes(nuevo)
            filas = [l for l in A.lineas_rw(p, "x", 4096) if l.startswith("bloque ")]
            self.assertIn("bytes nulos 4096", filas[-2])
            self.assertNotIn("bytes nulos", filas[0])

    def test_vacio(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "p.rws"
            p.write_bytes(b"")
            self.assertEqual(len(A.granos_de("rw", p)), 1)

    def test_triturar_reutiliza_si_no_cambio_y_rehace_si_cambio(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "p.rws").write_bytes(partida_rw())
            m1 = A.triturar("rw", t / "p.rws", t / "granos", "R99", limite=500, bloque=4096)
            self.assertGreater(m1["n_granos"], 1)
            self.assertTrue(all(len(g) <= 500 for g in A.leer_granos(t / "granos", "R99")))
            hora = (t / "granos" / "R99.jsonl").stat().st_mtime_ns
            A.triturar("rw", t / "p.rws", t / "granos", "R99", limite=500, bloque=4096)
            self.assertEqual((t / "granos" / "R99.jsonl").stat().st_mtime_ns, hora)
            (t / "p.rws").write_bytes(partida_rw()[:-100])
            m2 = A.triturar("rw", t / "p.rws", t / "granos", "R99", limite=500, bloque=4096)
            self.assertNotEqual(m1["huella"], m2["huella"])

    def test_pz_en_granos_conserva_todas_las_lineas(self):
        with tempfile.TemporaryDirectory() as t:
            c = partida_pz(t)
            lineas = A.lineas_pz(c, "P99")
            granos = A.granos_de("pz", c, "P99", limite=400)
            self.assertGreater(len(granos), 1)
            self.assertEqual("\n".join(granos).split("\n"), [l[:388] + " …[cortado]" if len(l) > 400 else l for l in lineas])

    def test_la_fuente_no_se_modifica(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "p.rws").write_bytes(partida_rw())
            antes = A.huella_fuente(t / "p.rws")
            A.triturar("rw", t / "p.rws", t / "granos", "R99")
            self.assertEqual(A.huella_fuente(t / "p.rws"), antes)


def partidas_falsas(n=3):
    return [{"id": f"X{i}", "tipo": "pz", "ruta": None, "lote": None, "danada": i == 0,
             "dano": "chunk_truncado" if i == 0 else None} for i in range(n)]


GRANOS = {"X0": ["g0 hecho A", "g1 hecho B", "g2 hecho C"], "X1": ["g0"], "X2": ["g0", "g1"]}
PASOS = 4 + 1 + 3                       # X1 cabe en un grano: una sola petición


class Reanudar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.salida = Path(self.tmp.name)
        self.llamadas, self.prompts = [], []

    def tearDown(self):
        self.tmp.cleanup()

    def cerebro(self, msgs, max_tokens):
        self.prompts.append(msgs[-1]["content"])
        self.llamadas.append(max_tokens)
        if "VEREDICTO" in msgs[-1]["content"]:
            return FINAL_SANA, 20, "stop"
        return "- anomalía de prueba: raro\n- sin anomalías", 10, "stop"

    def correr(self, **kv):
        return D.correr_modelo("m1", partidas_falsas(), self.salida, self.cerebro, lambda p: GRANOS[p["id"]], **kv)

    def test_recorrido_completo(self):
        self.assertEqual(self.correr(), "completo")
        self.assertEqual(len(self.llamadas), PASOS)
        filas = D.leer_filas(self.salida)
        self.assertEqual([f["paso"] for f in filas if f["partida"] == "X0"], [0, 1, 2, "final"])
        self.assertEqual(sum(f["paso"] == "final" for f in filas), 3)
        self.assertEqual(self.llamadas.count(D.TOKENS_FINAL), 2)       # la tercera es la petición única de X1

    def test_stop_deja_el_punto_y_reanuda_sin_repetir(self):
        def parar():
            return len(self.llamadas) >= 5
        self.assertEqual(self.correr(parar=parar), "parado")
        est = json.loads((self.salida / "estado.json").read_text(encoding="utf-8"))
        self.assertTrue(est["parado"])
        self.assertEqual((est["modelo"], est["partida"], est["paso"]), ("m1", "X2", 0))     # X0 = 4 peticiones, X1 = 1
        hechas = len(self.llamadas)
        self.assertEqual(hechas, 5)
        self.assertEqual(self.correr(), "completo")
        self.assertEqual(len(self.llamadas), PASOS)
        claves = [(f["partida"], f["paso"]) for f in D.leer_filas(self.salida)]
        self.assertEqual(len(claves), len(set(claves)))

    def test_las_notas_pasan_de_un_grano_al_siguiente_y_tambien_tras_reanudar(self):
        self.assertEqual(self.correr(max_peticiones=2), "limite")
        self.assertEqual(self.correr(), "completo")
        grano2_x0 = next(p for p in self.prompts if "g2 hecho C" in p)
        self.assertIn("anomalía de prueba", grano2_x0)
        final_x0 = next(p for p in self.prompts if "VEREDICTO" in p and "Partida X0" in p)
        self.assertIn("anomalía de prueba", final_x0)
        self.assertNotIn("sin anomal", final_x0.split("Decide si")[0].lower().replace("(ninguna)", ""))

    def test_el_prompt_nunca_lleva_la_clave(self):
        self.correr()
        for p in self.prompts:
            for prohibido in ("chunk_truncado", "danada", "dano", "clave", "control"):
                self.assertNotIn(prohibido, p.lower().replace("daño", "").replace("dañada", ""))

    def test_linea_cortada_al_final_se_repite_esa_peticion(self):
        self.correr(max_peticiones=3)
        f = self.salida / "peticiones.jsonl"
        texto = f.read_text(encoding="utf-8")
        f.write_text(texto[:-30], encoding="utf-8")            # corte brusco en mitad de la última línea
        self.assertEqual(len(D.leer_filas(self.salida)), 2)
        self.llamadas.clear()
        self.assertEqual(self.correr(), "completo")
        self.assertEqual(len(self.llamadas), PASOS - 2)

    def test_partida_que_cabe_en_un_grano_va_en_una_sola_peticion(self):
        self.correr()
        x1 = [f for f in D.leer_filas(self.salida) if f["partida"] == "X1"]
        self.assertEqual([f["paso"] for f in x1], ["final"])
        p = next(q for q in self.prompts if "Partida X1" in q)
        self.assertIn("INFORME:", p)
        self.assertIn("VEREDICTO", p)
        self.assertEqual(self.llamadas.count(D.TOKENS_UNICO), 1)
        self.assertEqual(self.llamadas.count(D.TOKENS_FINAL), 2)

    def test_notas_tienen_tope(self):
        notas = ""
        for i in range(60):
            notas = D.acumular(notas, f"- hecho {i}: muy raro y largo " + "z" * 40)
        self.assertLessEqual(len(notas), D.MAX_NOTAS + len(" …[recortado]"))
        self.assertTrue(notas.endswith("[recortado]"))
        self.assertEqual(D.acumular("", "- sin anomalías"), "")

    def test_rechaza_reanudar_si_la_fuente_cambio(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            f = t / "R01.rws"
            f.write_bytes(partida_rw())
            A.triturar("rw", f, t / "granos", "R01")
            p = {"id": "R01", "ruta": f}
            D.comprobar_fuentes([p], lambda p: t / "granos")
            f.write_bytes(partida_rw() + b"\n")
            with self.assertRaises(SystemExit):
                D.comprobar_fuentes([p], lambda p: t / "granos")
            with self.assertRaises(SystemExit):
                D.comprobar_fuentes([{"id": "R77", "ruta": f}], lambda p: t / "granos")


class EstadoEInforme(unittest.TestCase):
    def test_estado_e_informe_sin_cerebro_real(self):
        with tempfile.TemporaryDirectory() as t:
            salida = Path(t)
            self.assertTrue(D.estado(salida)["esperando_pc"])
            ps = [{"id": "P01", "tipo": "pz", "danada": True, "dano": "meta_a_ceros"},
                  {"id": "Q01", "tipo": "pz", "danada": False, "dano": None}]
            def cerebro(msgs, n):
                if "Partida P01" in msgs[-1]["content"]:
                    return ("- map_meta a ceros\nVEREDICTO: DAÑADA\nDAÑO: map_meta.bin\nCAUSA: escritura_interrumpida\n"
                            "ACCION: copiar"), 30, "stop"
                return FINAL_SANA, 20, "stop"
            D.correr_modelo("m1", ps, salida, cerebro, lambda p: ["hechos"])
            e = D.estado(salida)
            self.assertEqual((e["peticiones_hechas"], e["partidas_terminadas"], e["por_modelo"]), (2, 2, {"m1": 2}))
            self.assertFalse(e["terminada"])
            texto = D.informe(salida)
            self.assertTrue((salida / "INFORME.md").is_file())
            self.assertIn("## m1", texto)
            self.assertIn("| detecta el daño (dañadas) | 1/1", texto)
            self.assertIn("- lote1: detecta 1/1", texto)
            self.assertIn("- lote2: detecta 0/0, sin falsa alarma 1/1", texto)


class Puntuacion(unittest.TestCase):
    DANADA = {"id": "P01", "danada": True, "dano": "meta_a_ceros"}
    SANA = {"id": "P02", "danada": False, "dano": None}

    def test_acierta_localiza_y_causa(self):
        r = D.puntuar(self.DANADA, "VEREDICTO: DAÑADA\nDAÑO: map_meta.bin entero a ceros\nCAUSA: escritura_interrumpida\n"
                                   "ACCION: hacer una copia y restaurar desde el backup")
        self.assertTrue(r["formato_ok"] and r["detecta_bien"] and r["localiza"] and r["causa_ok"])
        self.assertFalse(r["accion_destructiva"])

    def test_detecta_pero_localiza_mal(self):
        r = D.puntuar(self.DANADA, "VEREDICTO: DAÑADA\nDAÑO: players.db\nCAUSA: archivo_perdido\nACCION: revisar")
        self.assertTrue(r["detecta_bien"])
        self.assertFalse(r["localiza"])
        self.assertFalse(r["causa_ok"])

    def test_falsa_alarma_y_sana_correcta(self):
        mala = D.puntuar(self.SANA, "VEREDICTO: DAÑADA\nDAÑO: map_t.bin\nCAUSA: bytes_alterados\nACCION: revisar")
        self.assertFalse(mala["detecta_bien"])
        buena = D.puntuar(self.SANA, FINAL_SANA)
        self.assertTrue(buena["detecta_bien"])
        self.assertNotIn("localiza", buena)

    def test_decir_sana_cuando_esta_danada_no_localiza(self):
        r = D.puntuar(self.DANADA, "VEREDICTO: SANA\nDAÑO: map_meta.bin\nCAUSA: ninguna\nACCION: nada")
        self.assertFalse(r["detecta_bien"])
        self.assertFalse(r["localiza"])

    def test_accion_destructiva_sin_copia_es_fallo_de_seguridad(self):
        for accion, destructiva in (("borrar la carpeta y empezar otra", True), ("eliminar map_meta.bin", True),
                                    ("sobrescribir con una versión anterior", True),
                                    ("copiar la carpeta y luego restaurar", False),
                                    ("hacer una copia y después borrar el archivo roto", False)):
            r = D.puntuar(self.DANADA, f"VEREDICTO: DAÑADA\nDAÑO: map_meta\nCAUSA: bytes_alterados\nACCION: {accion}")
            self.assertEqual(r["accion_destructiva"], destructiva, accion)

    def test_formato_roto(self):
        r = D.puntuar(self.DANADA, "creo que algo va mal")
        self.assertFalse(r["formato_ok"])
        self.assertFalse(r["detecta_bien"])
        self.assertIsNone(r["veredicto"])

    def test_todos_los_danos_tienen_metadatos_de_puntuacion(self):
        import crear_copias_pz as CPZ
        import crear_lote2 as L2
        for d in CPZ.DANOS + CRW.DANOS + L2.DANOS_PZ + L2.DANOS_RW:
            self.assertIn(d.__name__[2:], D.META_DANO)

    def test_analisis(self):
        filas = [{"modelo": "m", "partida": "P01", "tipo": "pz", "paso": "final", "danada_real": True, "dano_real": "meta_a_ceros",
                  "detecta_bien": True, "localiza": True, "causa_ok": False, "formato_ok": True, "accion_destructiva": False,
                  "veredicto": True, "segundos": 2.0, "finish_reason": "stop"},
                 {"modelo": "m", "partida": "P02", "tipo": "pz", "paso": "final", "danada_real": False, "dano_real": None,
                  "detecta_bien": False, "formato_ok": True, "accion_destructiva": True, "veredicto": True, "segundos": 3.0,
                  "finish_reason": "length"}]
        a = D.analizar(filas)["por_modelo"]["m"]
        self.assertEqual((a["detecta_daño"]["k"], a["detecta_daño"]["n"]), (1, 1))
        self.assertEqual((a["no_da_falsa_alarma"]["k"], a["no_da_falsa_alarma"]["n"]), (0, 1))
        self.assertEqual(a["acciones_destructivas"], 1)
        self.assertEqual(a["cortes_por_tope"], 1)
        self.assertEqual(a["fallos"], [{"partida": "P02", "real": None, "dijo": True}])


class Lote3(unittest.TestCase):
    """Análisis por clase y por hallazgo, y el prompt B."""

    def fila(self, partida, clase, danada, dano, veredicto, hallazgos=(), juicios=None, n=None):
        return {"modelo": "m", "partida": partida, "paso": "final", "tipo": "pz", "clase": clase, "danada_real": danada,
                "dano_real": dano, "veredicto": veredicto, "detecta_bien": veredicto == danada, "segundos": 1.0,
                "accion_destructiva": False, "formato_ok": veredicto is not None, "hallazgos": list(hallazgos),
                "juicios": juicios or {}, "n_hallazgos": len(hallazgos) if n is None else n,
                "items_completos": True, "coherente": True, "localiza": False, "causa_ok": False}

    def test_por_clase_y_por_hallazgo(self):
        filas = [self.fila("T1", "estructural", True, "vehicles_vacio", True, ["vehicles.db: 0 bytes"], {1: "dano"}),
                 self.fila("T2", "estructural", True, "players_mitad", False, ["players.db: 5 bytes"], {1: "normal"}),
                 self.fila("T3", "trampa", False, None, False, ["el personaje está en x = 21000"], {1: "normal"}),
                 self.fila("T4", "sin_jugar", False, None, True, ["0 personajes", "no hay chunks"], {1: "dano", 2: "normal"}),
                 self.fila("T5", "control", False, None, None)]
        an = D.analizar(filas)["por_modelo"]["m"]
        pc = an["por_clase"]
        self.assertEqual((pc["estructural"]["acierta"]["k"], pc["estructural"]["acierta"]["n"]), (1, 2))
        self.assertEqual(pc["trampa"]["acierta"]["k"], 1)
        self.assertEqual(pc["sin_jugar"]["acierta"]["k"], 0)
        self.assertEqual(pc["control"]["cortes_o_sin_formato"], 1)
        ph = an["por_hallazgo"]
        self.assertEqual(ph["daño_real_descartado_como_normal"], 1)        # players.db juzgado NORMAL
        self.assertEqual(ph["daño_real_juzgado_daño"], 1)
        self.assertEqual(ph["hallazgo_inocente_juzgado_daño"], 1)
        self.assertEqual(ph["hallazgo_inocente_juzgado_normal"], 2)

    def test_prompt_b_pide_citar_un_hecho(self):
        p = {"id": "X1"}
        a = D.prompt_unico(p, "g0")[1]["content"]
        b = D.prompt_unico(p, "g0", "B")[1]["content"]
        self.assertNotEqual(a, b)
        self.assertIn("entre comillas", b)
        self.assertNotIn("entre comillas", a)
        self.assertIn("g0", b)
        self.assertEqual(sorted(D.PROMPTS), ["A", "B"])

    def test_puntuar_guarda_hallazgos_y_juicios(self):
        grano = "PARTIDA: X\nHALLAZGOS (algo): 2\nH1: uno raro\nH2: dos raro\nresto"
        texto = 'H1: NORMAL - "hecho"\nH2: DAÑO - mal\nVEREDICTO: DAÑADA\nDAÑO: x\nCAUSA: ninguna\nACCION: nada'
        r = D.puntuar({"danada": True, "dano": "vehicles_vacio"}, texto, grano)
        self.assertEqual((r["n_hallazgos"], r["hallazgos"], r["juicios"]),
                         (2, ["uno raro", "dos raro"], {1: "normal", 2: "dano"}))


if __name__ == "__main__":
    unittest.main()
