# Desafío PZ — diagnóstico estático para Equipo IA

Material: extractos de un registro de Project Zomboid previamente proporcionado por el usuario. Son evidencias reales, pero no una reproducción controlada de un fallo. No se incluyen archivos originales del juego ni código propietario.

Objetivo: A2 identifica hechos e hipótesis; A1 propone pasos y parches hipotéticos no ejecutados; A3 cuestiona evidencia, riesgos y conclusiones.

Para cada caso entregar: observaciones citando L<numero> del log, hipótesis con confianza, datos faltantes, acciones de diagnóstico reversibles, plan de verificación y condición de falsación. NO afirmar que el log demuestra la causa de FPS bajos.

PROHIBIDO: ejecutar scripts generados, modificar instalación o partidas, descargar dependencias, declarar un arreglo verificado, atribuir culpabilidad de rendimiento a un mod sin prueba.

El registro original puede incluir eventos de distintas fases de carga; el orden y frecuencia de líneas aisladas no equivale a un perfil de CPU/GPU.

Uso: python3 -B generar_reto.py --seed 42. No requiere bibliotecas externas.
