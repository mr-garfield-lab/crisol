"""Corredor de unittest de la línea base V3: ESTADO EXACTO y FIRMA de cada prueba, en un proceso hijo.

Uso:  python3 -B -I corredor_unittest.py <dir_pruebas> <salida.json> [ruta_para_sys.path ...]

Estados (nunca se convierte un error en éxito):
  OK, FALLO (aserción), ERROR (excepción, fallo de carga del módulo o de setUp/setUpClass), OMITIDA (skip),
  FALLO_ESPERADO (expectedFailure que falla), EXITO_INESPERADO (expectedFailure que pasa: unittest lo
  cuenta como fallo).
Si unittest informa varias veces de la misma prueba (subtests, error en tearDown tras un fallo...), se conserva
el resultado MÁS GRAVE. La firma es «Tipo: primera línea … última línea» del mensaje; el proceso padre la
normaliza (rutas temporales) para que sea estable entre ejecuciones.
"""
import io
import json
import sys
import unittest

GRAVEDAD = {"OK": 0, "FALLO_ESPERADO": 1, "OMITIDA": 2, "EXITO_INESPERADO": 3, "FALLO": 4, "ERROR": 5}
# Cota de seguridad de cada línea CRUDA. No debe recortar antes de normalizar: el padre sustituye las rutas
# temporales y DESPUÉS recorta (MAX_FIRMA). Con un recorte de 240 caracteres aquí, la firma dependía de la
# LONGITUD de la carpeta de salida (defecto encontrado por el verificador integral de la Etapa 1).
MAX_LINEA_CRUDA = 8000


def ident(prueba) -> str:
    # El método de la CLASE: una prueba puede tapar `self.id` con un atributo propio
    # (test_complementos.py hace `self.id = ...`), y llamar a `prueba.id()` rompería el corredor.
    return type(prueba).id(prueba)


def firma(err) -> str:
    tipo, valor = err[0], err[1]
    lineas = [l.strip() for l in str(valor).splitlines() if l.strip()]
    texto = f"{tipo.__name__}: {lineas[0][:MAX_LINEA_CRUDA] if lineas else ''}"
    if len(lineas) > 1:                      # p. ej. _FailedTest: la causa real va en la última línea
        texto += f" … {lineas[-1][:MAX_LINEA_CRUDA]}"
    return texto


def main(argv) -> int:
    inicio, salida, *rutas = argv
    for p in reversed(rutas):
        sys.path.insert(0, p)
    pruebas = {}

    def anotar(prueba, estado, detalle=""):
        clave = ident(prueba)
        previo = pruebas.get(clave)
        if previo is None or GRAVEDAD[estado] > GRAVEDAD[previo["estado"]]:
            pruebas[clave] = {"estado": estado, "firma": detalle}

    class Resultado(unittest.TextTestResult):
        def addSuccess(self, t):
            super().addSuccess(t)
            anotar(t, "OK")

        def addFailure(self, t, e):
            super().addFailure(t, e)
            anotar(t, "FALLO", firma(e))

        def addError(self, t, e):
            super().addError(t, e)
            anotar(t, "ERROR", firma(e))

        def addSkip(self, t, motivo):
            super().addSkip(t, motivo)
            anotar(t, "OMITIDA", str(motivo)[:MAX_LINEA_CRUDA])

        def addExpectedFailure(self, t, e):
            super().addExpectedFailure(t, e)
            anotar(t, "FALLO_ESPERADO", firma(e))

        def addUnexpectedSuccess(self, t):
            super().addUnexpectedSuccess(t)
            anotar(t, "EXITO_INESPERADO", "expectedFailure que pasa")

        def addSubTest(self, t, sub, e):
            super().addSubTest(t, sub, e)
            if e is not None:
                anotar(t, "FALLO" if issubclass(e[0], t.failureException) else "ERROR", firma(e))

    suite = unittest.defaultTestLoader.discover(inicio, pattern="test_*.py", top_level_dir=inicio)
    registro = io.StringIO()
    res = unittest.TextTestRunner(stream=registro, verbosity=2, resultclass=Resultado).run(suite)
    with open(salida, "x", encoding="utf-8") as f:
        json.dump({"pruebas": pruebas, "ejecutadas": res.testsRun, "registro": registro.getvalue()}, f,
                  ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
