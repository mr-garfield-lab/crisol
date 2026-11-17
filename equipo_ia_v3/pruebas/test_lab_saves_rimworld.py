"""Pruebas del traductor de partidas de RimWorld (lab_saves) con partidas sintéticas: sin tocar las reales."""
import random
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_saves"))
import crear_copias_rimworld as C  # noqa: E402
import traductor_rimworld as T  # noqa: E402


def partida():
    """Partida mínima con la forma de una .rws sana, con relleno para que los daños por fracción caigan dentro."""
    cosas = "".join(f'<thing Class="{"Pawn" if n % 5 == 0 else "ThingWithComps"}"><def>Steel</def><id>Steel{n}</id>'
                    f'<pos>(1, 0, {n})</pos></thing>\n' for n in range(400))
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n<savegame>\n<meta>\n<gameVersion>1.6.4871 rev591</gameVersion>\n'
           '<modIds><li>brrainz.harmony</li><li>ludeon.rimworld</li></modIds>\n'
           '<modSteamIds><li>0</li><li>0</li></modSteamIds>\n<modNames><li>Harmony</li><li>Core</li></modNames>\n'
           '</meta>\n<game>\n<tickManager><ticksGame>60000</ticksGame></tickManager>\n'
           f'<maps>\n<li>\n<things>\n{cosas}</things>\n</li>\n</maps>\n<cameraMap />\n</game>\n</savegame>\n')
    return b"\xef\xbb\xbf" + xml.encode("utf-8")


class Traductor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name) / "p.rws"
        self.p.write_bytes(partida())

    def tearDown(self):
        self.tmp.cleanup()

    def test_sana(self):
        i = T.traducir(self.p)
        self.assertTrue(i["xml_valido"])
        self.assertTrue(i["termina_en_savegame"])
        self.assertEqual((i["maps"], i["things"], i["pawns"], i["ids_repetidos"]), (1, 400, 80, 0))
        self.assertEqual(i["meta"]["gameVersion"], "1.6.4871 rev591")
        self.assertEqual(set(i["meta"]["n_mods"].values()), {2})
        self.assertEqual(i["meta"]["ticksGame"], "60000")

    def test_solo_lectura(self):
        antes = C.PZ.huella_archivo(self.p)
        T.traducir(self.p)
        self.assertEqual(C.PZ.huella_archivo(self.p), antes)

    def test_cada_dano_es_visible_y_no_salta_en_sana(self):
        sana = T.traducir(self.p)
        for dano in C.DANOS:
            with self.subTest(dano=dano.__name__):
                nuevo, desc, comprobar = dano(partida(), random.Random(4))
                q = Path(self.tmp.name) / f"{dano.__name__}.rws"
                q.write_bytes(nuevo)
                self.assertTrue(comprobar(T.traducir(q)), desc)
                self.assertFalse(comprobar(sana), desc)

    def test_informe_sin_veredictos(self):
        nuevo, _, _ = C.d_truncado(partida(), random.Random(5))
        self.p.write_bytes(nuevo)
        texto = T.a_texto(T.traducir(self.p)).lower()
        for palabra in ("dañad", "corrupt", "sano", "roto"):
            self.assertNotIn(palabra, texto)

    def test_vacio(self):
        self.p.write_bytes(b"")
        self.assertIn("0 bytes", T.a_texto(T.traducir(self.p)))

    def test_no_sobrescribe_destino(self):
        with self.assertRaises(SystemExit):
            C.main(self.tmp.name)


if __name__ == "__main__":
    unittest.main()
