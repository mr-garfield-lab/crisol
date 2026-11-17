import unittest, tempfile, json, zipfile
from pathlib import Path
from laboratorio import inspect_zip,simulate
class TestLab(unittest.TestCase):
 def test_inventory(self):
  x=simulate({'acciones':[{'accion':'agregar','objeto':'a','cantidad':2},{'accion':'consumir','objeto':'a'},{'accion':'comprobar','objeto':'a','cantidad':1}]})
  self.assertTrue(x['todos_ok'])
 def test_inspection(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'mod.zip'
   with zipfile.ZipFile(p,'w') as z: z.writestr('media/lua/client/test.lua','Events.OnGameStart.Add(function() end)')
   x=inspect_zip(p)
   self.assertEqual(x['entradas'][0]['eventos_lua'],['OnGameStart'])
 def test_traversal(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'mod.zip'
   with zipfile.ZipFile(p,'w') as z: z.writestr('../escape.lua','x')
   x=inspect_zip(p)
   self.assertEqual(x['hallazgos'][0]['tipo'],'ruta_peligrosa')
 def test_no_false_success(self):
  self.assertFalse(simulate({'acciones':[{'accion':'consumir','objeto':'a'}]})['todos_ok'])
if __name__=='__main__': unittest.main()
