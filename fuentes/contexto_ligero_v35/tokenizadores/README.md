# Tokenización real opcional

`gpt2/tokenizer.json` es el vocabulario público GPT-2. El conteo usa la biblioteca
gratuita `tokenizers`, instalada en un directorio separado durante la validación.
La procedencia y los hashes del archivo y de la biblioteca deben consultarse en
los archivos de evidencia incluidos junto al vocabulario y en los resultados.

GPT-2 permite una medida real, reproducible y local del texto para **ese
tokenizador**. No se afirma que sea el tokenizador de Claude, de Codex ni de otros
modelos recientes. No incluye la plantilla de chat, instrucciones adicionales,
tokens especiales añadidos por un proveedor ni respuestas generadas.

El motor estándar continúa funcionando sin dependencias externas y etiqueta sus
conteos como estimados. Usar el JSON no instala ni descarga automáticamente nada.
Para contar con la biblioteca disponible en el entorno:

```sh
python -B contexto_v3.py tokens LEEME.md --tokenizer-json tokenizadores/gpt2/tokenizer.json
python -B EJECUTAR_PRUEBAS.py --tokenizer-json tokenizadores/gpt2/tokenizer.json
```

Si la biblioteca está en un directorio privado, añádalo al `PYTHONPATH` del proceso.
En el entorno de validación local se utiliza `/workspace/tokenizacion_v33/deps`.
No se incluyen binarios Linux x86_64 como dependencia obligatoria para Termux:
su instalación y funcionamiento en Android necesitan validación propia.

Para preparar un directorio local en un entorno compatible, con instalación
expresamente autorizada:

```sh
python -m pip install --no-deps --target .deps_tokenizer -r requirements-tokenizer.txt
PYTHONPATH=.deps_tokenizer python -B EJECUTAR_PRUEBAS.py --tokenizer-json tokenizadores/gpt2/tokenizer.json
```

Se descargan únicamente la biblioteca gratuita y, durante la preparación de esta
entrega, el vocabulario público incluido. No se enviaron textos del proyecto a un
servicio. `LIBRERIA_VALIDADA.json` registra versión y hashes de la instalación
comprobada. `gpt2/PROCEDENCIA.json` registra URLs/hashes del vocabulario y su licencia.

La entrega incluye el vocabulario y su licencia, pero no una biblioteca binaria
portable para todas las plataformas. Sin esa dependencia opcional, el motor y
las pruebas básicas funcionan; los cuatro tests reales se marcan como omitidos.

Los conteos desactivan truncamiento y relleno del JSON para medir todo el texto.
`tests/test_real_tokenizer.py` comprueba IDs conocidos de GPT-2, Unicode, español,
código, texto vacío y un JSON configurado para truncar/rellenar. Sin la biblioteca
o el vocabulario, estos casos se indican como **omitidos**, nunca como medición
real realizada. No envían el código del proyecto ni el texto a ningún servicio.
