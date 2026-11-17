# Banco local para evaluar modelos de IA: Blender y diagnóstico de partidas

Dos bancos independientes, en la misma imagen Docker, para medir qué saben hacer tus modelos de lenguaje **locales**
(ninguno se incluye ni se descarga aquí). Los dos usan el mismo patrón: el modelo responde, algo SIN IA lo comprueba
contra hechos, y si falla el modelo recibe esos hechos para corregir.

- **[`lab_blender/LEEME.md`](lab_blender/LEEME.md)**: el modelo escribe scripts de Blender (robots, animaciones…) y un
  verificador mide la escena resultante (medidas, posiciones, piezas unidas, movimiento). Necesita construir la imagen
  con Blender (descarga unos 400 MB) y, para los vídeos, una GPU que Blender pueda usar.
- **[`lab_saves/LEEME.md`](lab_saves/LEEME.md)**: el modelo diagnostica copias dañadas de **tus propias** partidas de
  Project Zomboid o RimWorld, a partir de un informe de hechos (nunca del binario). No necesita GPU ni descarga nada
  más; usa tus partidas, que montas tú mismo en modo lectura.

## Construir (una sola vez, sirve para los dos)
    docker build -t banco-local-ia .

## Seguridad y privacidad, en común
- **No se envía nada fuera** salvo a la URL de tu propio servidor de modelos (llama.cpp, Ollama, LM Studio…). Sin
  claves por defecto, sin telemetría.
- **El paquete no lleva modelos, resultados, partidas ni rutas de nadie.** El script que lo genera (`empaquetar.py`,
  no incluido aquí) revisa cada archivo antes de crear el ZIP.
- Cada banco ejecuta código que escribe un modelo (scripts de Blender) o solo lee archivos binarios que tú aportas
  (partidas). Lee el LEEME de cada uno antes de usarlo: ahí están las barreras concretas y sus límites.
- **Ninguno se ha construido ni probado dentro de Docker ni en Linux** por quien lo escribió: se desarrolló y probó
  en Windows. Cada LEEME trae un paso de validación para comprobarlo antes de gastar tiempo de modelo.

Ver `MANIFIESTO.json` para el SHA-256 de cada archivo del paquete.
