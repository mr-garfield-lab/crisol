# material_original/generar_reto.py — NO EJECUTAR

`material_original/` es una copia **byte a byte** del material Zomboid del encargo V2-E.6 (su `MANIFIESTO.json`
lo verifica). `generar_reto.py` se conserva solo para que el manifiesto original siga siendo comprobable.

* Equipo IA **nunca** lo importa ni lo ejecuta (el verificador lo comprueba: prueba
  `test_v2e6_retos.TestMaterial.test_generar_reto_original_nunca_se_ejecuta`).
* El generador seguro propio es `src/eq2/retos.py` (`generar(semilla)`), reimplementado a partir de una
  lectura del original, sin red, sin escritura y sin ejecutar nada.
* El equivalente exacto de su salida NO se ha verificado ejecutándolo (deliberadamente).

`eq2/` contiene los datos propios de Equipo IA: `casos.json` (lo que ven los agentes), `oraculos.json`
(OCULTO: nunca entra en un prompt) y `referencias.json` (respuestas buena/mala escritas a mano para calibrar
el puntuador; no son salidas de Qwen).
