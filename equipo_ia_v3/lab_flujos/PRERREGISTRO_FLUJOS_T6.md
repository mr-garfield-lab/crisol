# Preregistro: banco de flujos grandes, tanda 6 (código REAL con preguntas naturales)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
Las tandas 1–5 usan un corpus sintético con nombres deliberadamente parecidos entre sí. ¿Cómo le va al sistema con el
código de verdad del propio Equipo IA (`sistema/src/eq2`: 68 archivos, ~1,13 MB, unas 90 veces el contexto de 4096) y
preguntas escritas como las haría una persona, sin nombres de variables?

## Montaje
- 24 preguntas (`lab_flujos/generar_corpus.py`, `tareas_t6`, sin azar; el corpus sintético no cambia):
  - **N1–N18, naturales**: «¿Cuántos tokens como máximo puede pedir el sistema en una sola respuesta del modelo?».
    Cada una corresponde a UNA constante; la respuesta se lee del código con `ast` al generar (no está escrita a mano).
    Donde dos constantes podían confundirse (llamadas por tarea frente a las del motor) se pregunta por las dos.
  - **X1–X4, exactas**: con el nombre (`MARGEN_CTX`, `MIN_TOKENS_CONTINUACION`, `MAX_CASOS`, `MAX_CHARS`).
  - **U1–U2, trampas**: un nombre inexistente (`MAX_REINTENTOS_RED`) y un dato que el código no tiene (VRAM mínima en
    GB); se comprueba con `ast` que no existen.
- Condiciones: `ligero` (Contexto Ligero, ya con constantes de módulo) e `identidad` (claves verificadas → lista de
  nombres → elección o NINGUNA → código exacto → cita y comprobación literal).
- Cerebros qwen25 y ministral3; contexto 4096; temperatura 0. Mismo armazón de seguridad.

## Medido antes, sin cerebro
- Cobertura de `ligero`: N 10/18, X 4/4. En el código real los nombres son descriptivos y comparten palabras con la
  pregunta, al contrario que en el corpus sintético (0/23 con paráfrasis).

## Reglas de decisión (fijadas antes de ver resultados)
- **Exactas**: al menos 3 de 4 en las dos condiciones y cerebros.
- **La identidad aporta en código real** si, en los DOS cerebros, acierta al menos 3 preguntas N más que `ligero`.
  Con 1 o menos, no aporta.
- **Fiable en código real** si, por cerebro y condición, las respuestas con un valor equivocado (en N, X y las
  trampas) son 3 o menos de 24.
- Se informa además del coste (llamadas, tokens, segundos) y, en `identidad`, de la elección correcta.

## Repetición en otro PC
Esta tanda va también en el paquete para repetirla en paralelo en otro equipo (`GUIA_AMIGO_BANCOS.md`). Las
preguntas, el código y los oráculos son idénticos; solo cambia la máquina.

## Resultado (2026-11-15; código real, sin paradas)

| | qwen25 ligero | qwen25 identidad | ministral3 ligero | ministral3 identidad |
|---|---|---|---|---|
| Aciertos (de 24) | 16 | 18 | 16 | 17 |
| Naturales N (de 18) | 10 | **13** | 10 | **13** |
| Exactas X (de 4) | 4 | 3 | 4 | 2 |
| Trampas U (de 2) | 2 | 2 | 2 | 2 |
| Respuestas con valor equivocado | 1 | 4 | 0 | 4 |

Veredictos según las reglas fijadas:
- **Exactas (≥ 3/4 en todo): NO** — ministral3 con identidad, 2/4. Con `ligero`, 4/4 en los dos.
- **La identidad aporta en código real: SÍ** (+3 preguntas naturales en los dos cerebros; umbral +3).
- **Fiable (≤ 3 valores equivocados): SÍ con `ligero` (1 y 0); NO con identidad (4 y 4).**
- Las dos trampas, bien en todo (nadie se inventó el dato inexistente).

Lectura: en código real (nombres descriptivos), Contexto Ligero solo ya acierta 16/24 casi sin equivocarse; la
identidad recupera preguntas naturales que la búsqueda no encuentra, pero se equivoca más.
**Cálculo posterior, NO prerregistrado:** Contexto Ligero primero y, solo si contesta «NO_ENCONTRADO», la identidad:
**qwen25 21/24 (3 fallos) y ministral3 23/24 (1 fallo)**, lo mejor de todas las condiciones. Pendiente de confirmar
con su propia tanda prerregistrada (tanda 7).
