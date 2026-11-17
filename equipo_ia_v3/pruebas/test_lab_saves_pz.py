"""Pruebas del traductor de partidas de Project Zomboid (lab_saves) con partidas sintéticas: sin tocar las reales."""
import random
import shutil
import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_saves"))
import crear_copias_pz as C  # noqa: E402
import traductor_pz as T  # noqa: E402

V = 249


def partida(base):
    """Partida mínima con la forma de una B42 sana."""
    c = Path(base) / "partida"
    (c / "map" / "10").mkdir(parents=True)
    texto = "Mapa A;Mapa B"
    (c / "map_ver.bin").write_bytes(struct.pack(">ii", V, len(texto)) + texto.encode("utf-16-be"))
    for nombre, firma in (("map_t.bin", b"GMTM"), ("map_meta.bin", b"META"), ("map_animals.bin", b"ZONE"),
                          ("gos_trap.bin", b"GLOS")):
        (c / nombre).write_bytes(firma + struct.pack(">i", V) + bytes(range(1, 60)))
    (c / "map.bin").write_bytes(bytes(12))
    (c / "WorldDictionary.bin").write_bytes(b"\x00\x00\x00\x01" + b"x" * 40)
    for y in range(12):
        (c / "map" / "10" / f"{y}.bin").write_bytes(b"\x00\x00\x00\x00" + bytes([V]) + bytes(range(1, 200)))
    for db, sql in (("players.db", "create table localPlayers(id, name, wx, wy, x, y, z, worldversion, data, isDead)"),
                    ("vehicles.db", "create table vehicles(id, wx, wy, x, y, inMeta, worldversion, data)")):
        con = sqlite3.connect(c / db)
        con.execute(sql)
        if db == "players.db":
            con.execute("insert into localPlayers(id, name, worldversion, isDead) values (1, 'Ana', ?, 0)", (V,))
        else:
            con.execute("insert into vehicles(id, worldversion) values (1, ?)", (V,))
        con.commit()
        con.close()
    return c


class Traductor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = partida(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sana(self):
        i = T.traducir(self.c)
        self.assertEqual(i["faltan"], [])
        self.assertEqual(i["versiones_en_cabeceras"].keys(), {str(V)})
        self.assertEqual(i["map_ver"]["bytes"], i["map_ver"]["bytes_si_cuadra"])
        self.assertEqual(i["chunks"]["total"], 12)
        self.assertEqual(i["chunks"]["cabeceras_distintas"], 1)
        self.assertEqual(i["players_db"]["comprobacion"], "ok")
        self.assertEqual(i["players_db"]["contenido"][0]["name"], "Ana")

    def test_solo_lectura(self):
        antes = C.huella(self.c)
        T.traducir(self.c)
        self.assertEqual(C.huella(self.c), antes)

    def test_informe_sin_veredictos(self):
        for f in (C.d_meta_a_ceros, C.d_sin_players):
            f(self.c, random.Random(1))
        texto = T.a_texto(T.traducir(self.c)).lower()
        for palabra in ("dañad", "corrupt", "sano", "roto", "error grave"):
            self.assertNotIn(palabra, texto)

    def test_cada_dano_es_visible(self):
        for dano in C.DANOS:
            with self.subTest(dano=dano.__name__), tempfile.TemporaryDirectory() as t:
                c = partida(t)
                desc, comprobar = dano(c, random.Random(2))
                self.assertTrue(comprobar(T.traducir(c)), desc)

    def test_ningun_dano_salta_en_una_sana(self):
        i = T.traducir(self.c)
        for dano in C.DANOS:
            with self.subTest(dano=dano.__name__), tempfile.TemporaryDirectory() as t:
                _, comprobar = dano(partida(t), random.Random(3))
                self.assertFalse(comprobar(i))

    def test_base_de_datos_ilegible(self):
        C.a_ceros(self.c / "players.db", 4096)
        d = T.traducir(self.c)["players_db"]
        self.assertFalse(d["cabecera_sqlite"])
        self.assertIn("error_sqlite", d)

    def test_formato_b41(self):
        (self.c / "map" / "10").rename(self.c / "viejo")
        for n, p in enumerate(sorted((self.c / "viejo").iterdir())):
            p.rename(self.c / f"map_1_{n}.bin")
        i = T.traducir(self.c)
        self.assertEqual(i["chunks"]["formato"], "map_X_Y.bin")
        self.assertEqual(i["chunks"]["total"], 12)

    def test_fechas_distintas_se_anotan(self):
        import os
        self.assertEqual(T.traducir(self.c)["fechas"]["otro_dia"], {})
        q = self.c / "map_t.bin"
        viejo = q.stat().st_mtime - 400 * 86400
        os.utime(q, (viejo, viejo))
        fe = T.traducir(self.c)["fechas"]
        self.assertEqual(list(fe["otro_dia"]), ["map_t.bin"])
        self.assertIn("en otro día: map_t.bin", T.a_texto(T.traducir(self.c)))

    def test_no_sobrescribe_destino(self):
        with self.assertRaises(SystemExit):
            C.main(self.tmp.name)


class Habitual(unittest.TestCase):
    """Rangos normales: se miden en partidas sanas y se muestran junto a cada archivo (solo hechos)."""

    def test_medir_y_mostrar(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as molde:
            origen = Path(d)
            modelo = partida(molde)
            for k in range(6):                                  # 6 partidas sintéticas en una carpeta de origen
                shutil.copytree(modelo, origen / f"p{k}")
            (origen / "p9_crash").mkdir()
            destino = origen / "hab.json"
            hab = T.medir_habitual(origen, excluir={"p0"}, destino=destino)
            self.assertEqual(hab["partidas"], 5)                # sin p0 (excluida) ni la «crash»
            self.assertEqual(hab["excluidas"], ["p0"])
            r = hab["archivos"]["map_meta.bin"]
            self.assertEqual((r["n"], r["bytes"][0] <= r["bytes"][1]), (5, True))
            self.assertEqual(hab["map_ver_bytes_de_mas"], [0])
            inf = T.traducir(origen / "p1", "X")
            self.assertIn("[normal:", T.a_texto(inf, habitual=hab))
            self.assertIn("lo normal en 5 partidas", T.a_texto(inf, habitual=hab))
            self.assertNotIn("[normal:", T.a_texto(inf, habitual={"partidas": 5, "archivos": {}, "map_ver_bytes_de_mas": [0],
                                                                  "versiones_distintas_por_partida": [1],
                                                                  "partidas_con_archivos_en_otro_dia": 0}))

    def test_pocas_partidas_no_dan_referencia(self):
        hab = {"archivos": {"map_meta.bin": {"n": 2, "bytes": [1, 2], "ceros": [0.1, 0.2]}}}
        self.assertEqual(T._referencia({"archivo": "map_meta.bin", "bytes": 5}, hab), "")


class Hallazgos(unittest.TestCase):
    """El sensor compara con lo normal; no sabe de daños concretos y no da veredictos."""

    @classmethod
    def setUpClass(cls):
        import hallazgos as H
        cls.H = H
        cls.hab = {"partidas": 20, "archivos": {"map_meta.bin": {"n": 20, "bytes": [100, 200], "ceros": [0.5, 0.6]},
                                                "gos_*": {"n": 50, "bytes": [1, 9], "ceros": [0.1, 0.2]}},
                   "presentes": {"map_ver.bin": 20, "players.db": 20, "vehicles.db": 20, "chunks": 20},
                   "version_minoritaria_max_segun_mayoritaria": {"249": 1}, "map_ver_bytes_de_mas": [0],
                   "map_ver_caracteres": [5, 50], "dias_de_diferencia_max": 3,
                   "jugador": {"filas": [1, 2], "x": [100, 200], "y": [100, 200], "isDead": [0, 1],
                               "con_version_distinta_de_map_ver": 0},
                   "chunks": {"con_vacios": 0, "con_muestra_a_ceros": 0, "con_inicios_distintos": 0,
                              "con_chunks_pequenos": 0, "total": [5, 50]}}

    def base(self):
        return {"archivos_raiz": [{"archivo": "map_meta.bin", "bytes": 150, "fraccion_ceros": 0.55}],
                "versiones_en_cabeceras": {"249": ["a", "b", "c"]}, "chunks": {"total": 10, "vacios": 0,
                "muestra_enteramente_a_ceros": 0, "cabeceras_distintas": 1}, "fechas": {},
                "map_ver": {"bytes": 10, "bytes_si_cuadra": 10, "caracteres_declarados": 5, "version": 249},
                "players_db": {"comprobacion": "ok", "filas": 1, "contenido": [{"x": 150, "y": 150, "isDead": 0, "worldversion": 249}]},
                "vehicles_db": {"comprobacion": "ok", "filas": 0, "contenido": []}}

    def test_sano_no_da_hallazgos(self):
        self.assertEqual(self.H.hallazgos_pz(self.base(), self.hab), [])

    def test_fuera_de_rango_y_faltas(self):
        inf = self.base()
        inf["archivos_raiz"][0].update(bytes=500, fraccion_ceros=1.0)
        inf["versiones_en_cabeceras"] = {"249": ["a", "b", "c"], "238": ["d", "e"]}
        inf["map_ver"] = {"bytes": 30, "bytes_si_cuadra": 10, "caracteres_declarados": 1}
        txt = " | ".join(self.H.hallazgos_pz(inf, self.hab))
        for esperado in ("map_meta.bin: 500 bytes", "100% de bytes a cero", "2 archivos con versión distinta",
                         "map_ver.bin mide 30", "declara 1 caracteres", "map_ver.bin"):
            self.assertIn(esperado, txt)

    def test_trampa_isdead_no_es_hallazgo(self):
        inf = self.base()
        inf["players_db"] = {"comprobacion": "ok", "filas": 1, "contenido": [{"x": 150, "y": 150, "isDead": 1, "worldversion": 249}]}
        self.assertEqual(self.H.hallazgos_pz(inf, self.hab), [])

    def test_bloque_de_texto(self):
        L = self.H.a_lineas(["uno", "dos"], 20)
        self.assertTrue(L[0].endswith(": 2") and L[1] == "H1: uno" and L[2] == "H2: dos")
        self.assertTrue(self.H.a_lineas([], 20)[0].endswith("ninguno"))
        self.assertEqual(len(self.H.a_lineas(["x"] * 12, 20)), 1 + 8 + 1)

    def test_rimworld(self):
        hab = {"partidas": 9, "bytes": [100, 200], "con_bom": 9, "mapas": [1, 2], "peones": [5, 9], "versiones": ["1.6"],
               "ticks": [10, 99], "mods": [3, 4], "con_core": 9, "modids_repetidos": 0}
        sano = {"bytes": 150, "bom": True, "termina": True, "nulos": 0, "xml_valido": True, "error": None, "maps": 1,
                "things": 50, "pawns": 6, "ids_repetidos": 0, "version": "1.6", "ticks": "50",
                "n_mods": {"modIds": 3, "modSteamIds": 3, "modNames": 3}, "core": True, "mods_repetidos": 0}
        self.assertEqual(self.H.hallazgos_rw(sano, hab), [])
        mal = dict(sano, ticks="-3600", pawns=0, core=False, mods_repetidos=1, nulos=7)
        txt = " | ".join(self.H.hallazgos_rw(mal, hab))
        for esperado in ("ticksGame vale '-3600'", "0 peones", "ludeon.rimworld", "mods repetidos", "7 bytes nulos"):
            self.assertIn(esperado, txt)


if __name__ == "__main__":
    unittest.main()
