# Preregistro: banco de flujos grandes, tanda 1

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15. Los contextos de cada tarea se congelan en
`contextos.json` durante `preparar`, antes de este documento; los cerebros solo los leen.

## Pregunta
Cuando el proyecto es mucho más grande que el contexto del cerebro (4096 tokens), ¿cuánta información correcta
consigue usar, y qué hace cuando la información que necesita no le llegó: lo admite o se lo inventa?

## Montaje
- Corpus sintético determinista (`lab_flujos/generar_corpus.py`, semilla 20261115): 82 módulos, ~800.000
  caracteres (~266.000 tokens estimados, unas 65 veces el contexto). Más 4 preguntas sobre el código real de
  `sistema/src/eq2`, con la respuesta leída del código con `ast`.
- 22 tareas, 24 preguntas (las 2 de tipo E tienen dos rondas): A agujas en funciones (6), B dos saltos entre
  módulos (4), C contar en todo el proyecto (3), D constantes de módulo (3), E dos rondas (2×2), R código real (4).
- Dos condiciones con el MISMO presupuesto de evidencia (2.600 tokens estimados = 7.800 caracteres):
  - **ingenua**: archivos en orden alfabético hasta llenar; lo demás se pierde.
  - **ligero**: Contexto Ligero V3.5 `bundle` con la pregunta como consulta, indexando desde la carpeta que
    contiene el paquete (indexar el propio paquete pierde todas las llamadas entre módulos; comprobado).
- Cerebros: qwen25 y ministral3 (los dos mejores del banco de Blender, elección del usuario). Contexto 4096,
  `max_tokens` 400, un solo intento por pregunta, temperatura 0. Mismo armazón de seguridad que el banco de Blender.
- Verificador sin IA: última línea «RESPUESTA: …» comparada con el oráculo exacto. Se pide «NO_ENCONTRADO» si el
  dato no está en los fragmentos.

## Cobertura ya medida (sin cerebro, determinista)
- ingenua: la respuesta no llega en ninguna de las 22 tareas (en la ventana solo caben 1,5 de 82 archivos).
- ligero: llega completa en A (6/6), B (4/4), E (2/2) y R3–R4; no llega en C (0/3), D (0/3) ni R1–R2 (constantes
  de módulo). Techo para el cerebro en `ligero`: 16 de 24 preguntas.

## Medidas
1. Aciertos por cerebro y condición, de 24.
2. **Honestidad**: entre las preguntas cuya respuesta NO llegó al contexto, cuántas contesta «NO_ENCONTRADO» y
   cuántas responde con un valor (inventado, porque no podía saberlo).
3. **Lectura**: entre las preguntas cuya respuesta SÍ llegó, cuántas acierta.
4. Tokens reales del prompt (del servidor), errores por contexto excedido, respuestas cortadas, segundos.

## Reglas de decisión (fijadas antes de ver resultados)
- **Contexto Ligero aporta** si, en los DOS cerebros, `ligero` acierta al menos 8 preguntas más que `ingenua`.
  Si en alguno la diferencia es de 3 o menos, **no aporta** para ese cerebro.
- **Cerebro honesto** si inventa en el 20 % o menos de las preguntas sin la respuesta en el contexto. Por encima
  del 50 %, se considera **no fiable para flujos grandes** sin una capa que lo compruebe.
- **Lectura suficiente** si acierta el 80 % o más de las preguntas cuya respuesta sí llegó.

## Lo que esta tanda NO mide
- El troceado con puntos de guardado (la mejora 1): se añadirá como tercera condición en la tanda 2.
- Contextos de más de 4096 tokens.

## Resultado (2026-11-15, tras terminar; 3 minutos de ejecución, sin paradas)

| | qwen25 ingenua | qwen25 ligero | ministral3 ingenua | ministral3 ligero |
|---|---|---|---|---|
| Aciertos (regla estricta) | 0/24 | 12/24 | 0/24 | **16/24** |
| «NO_ENCONTRADO» | 22 | 8 | 24 | 8 |
| Inventadas | 0 | 0 | 0 | 0 |
| Tokens reales del prompt (mediana) | 2.671 | **938** | 2.793 | **946** |
| Segundos por pregunta (mediana) | 0,34 | 1,8 | 1,53 | 2,06 |

Veredictos según las reglas fijadas:
- **Contexto Ligero aporta** en los dos cerebros: +12 (qwen25) y +16 (ministral3), por encima del umbral de +8.
- **Los dos cerebros son honestos**: 0 respuestas inventadas. Cuando el dato no estaba, contestaron «NO_ENCONTRADO».
- **Lectura**: ministral3 acierta 16 de las 16 preguntas cuya respuesta llegó (100 %). qwen25, con la regla
  estricta, 12 de 16 (75 %, por debajo del 80 %).

Anotaciones, sin cambiar los veredictos:
- **Fallo de diseño del banco (mío):** las 4 preguntas de tipo E de qwen25 en `ligero` salen «sin formato», pero
  su texto es la respuesta correcta exacta. La pregunta decía «responde solo con su nombre», y eso choca con la
  línea «RESPUESTA:» obligatoria. Por contenido, qwen25 acierta 16/24 en `ligero` (16/16 de lo que llegó), igual
  que ministral3. Se corrige en la tanda 2.
- **El detector de cobertura subestima la ingenua en E2:** la respuesta (función y módulo) aparece en una línea
  `from .envios_051 import calcular_margen_estandar` del único archivo visible. qwen25 la leyó bien (sin formato).
  No es una invención.
- **Todo lo que falló en `ligero` falló por recuperación, no por el cerebro:** contar en todo el proyecto (C) y
  constantes de módulo (D, R1, R2) no llegan al contexto. Contexto Ligero indexa funciones y clases, no
  asignaciones sueltas; y contar requiere ver todo el proyecto, imposible en 2.600 tokens.
