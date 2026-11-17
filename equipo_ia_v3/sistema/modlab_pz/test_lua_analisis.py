import unittest
from lua_analisis import analizar_lua, comprobar_sintaxis_archivo
from pathlib import Path
class TestLua(unittest.TestCase):
    def test_evento(self):
        x=analizar_lua(b'Events.OnGameStart.Add(func)', 'x.lua')
        self.assertEqual(x['eventos'],['OnGameStart'])
        self.assertFalse(x['ejecutado'])
    def test_riesgo(self):
        x=analizar_lua(b'os.execute("echo")')
        self.assertIn('os.execute',x['patrones_revision_manual'])
    def test_sin_falsas_promesas(self):
        x=analizar_lua(b'print("ok")')
        self.assertEqual(x['sintaxis'],'no_comprobada')
    def test_fixture_sintaxis(self):
        x=comprobar_sintaxis_archivo(str(Path(__file__).parent/'fixtures'/'mod_ejemplo_propio.lua'))
        self.assertIn(x['estado'],('no_disponible','sintaxis_valida'))
if __name__=='__main__':unittest.main()
