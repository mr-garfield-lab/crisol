# Preregistro: gemma12 (Gemma 4 12B QAT) en el banco de Blender

Escrito ANTES de preguntarle nada al cerebro. Fecha: 2026-11-15.

## Pregunta
¿Un cerebro más potente que 8B, de otra familia (Google), hace mejor las tareas que qwen25 (Qwen) y ministral3 (Mistral)?

## Cerebro
`gemma-4-12B-it-qat-UD-Q4_K_XL.gguf`, unsloth, revisión 980b060c40a8539ac159e0501a3e0f66a6365af3, 6 716 356 800 bytes,
SHA-256 90fd44e2…c940c370 (coincide con el publicado). Registrado en `cerebros_extra.json`, no en los registros de F1.
Prueba de carga: llama.cpp b12110 lo carga (arquitectura gemma4, 48 capas). Con el tope de VRAM solo caben 30 capas
en la GPU (4570 MiB); el resto va en la RAM, así que será más lento que los otros dos (4,1 tok/s medido con un juego
abierto). La velocidad NO cuenta para decidir (calidad ante todo).

## Qué se corre (mismo código y condiciones que los otros dos)
1. Como la 13c: T05, T08, T13 y T14, condición `fases`. Referencia: qwen25 137, ministral3 113.
2. Como la 13d: T14, condición `trozos`. Referencia: qwen25 53, ministral3 53.
800 tokens, 3 intentos por fase, verificador estricto, `--permitir_uso`.

## Sesgo conocido
Los avisos e instrucciones del banco se afinaron viendo los fallos de qwen25 y ministral3; si gemma12 tropieza con
algo que solo es costumbre de los otros dos, se anota, pero no se le cambia nada en esta prueba.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Entra en el equipo** si su suma en (1) es ≥ 137 (la mejor de los dos) y aprueba T05.
2. **Aporta en lo complicado** si aprueba T13 o T14 (por fases o por trozos).
3. Se informa: llamadas, respuestas cortadas, avisos que ignora (mismo error repetido) y segundos por respuesta.

## Resultados (2026-11-15, 19:43–19:58, sin cortes; 38 capas en la GPU por fases, 39 por trozos)

| | T05 | T08 | T13 | T14 fases | suma fases | T14 trozos |
|---|---|---|---|---|---|---|
| qwen25 (13c / 13d) | 28 ✓ | 35 ✓ | 21 | 53 | 137 | 53 |
| ministral3 (13c / 13d) | 28 ✓ | 35 ✓ | 50 ✓ | 0 | 113 | 53 |
| **gemma12** | **28 ✓** | **35 ✓** | **50 ✓** | 53 (relaciones a 81/82) | **166** | **82 ✓** |

1. **Entra en el equipo: sí.** Suma 166 ≥ 137 y aprueba T05.
2. **Aporta en lo complicado: sí.** Aprueba T13 por fases y **T14 por trozos (82/82): es la primera vez que un
   cerebro aprueba T14**, en 7 llamadas.
3. Recuentos:
   - Llamadas: 20 por fases + 7 por trozos. Una respuesta cortada (T14 piezas por fases, 800 tokens); ninguna por trozos.
   - Fallo propio repetido: en las tres tareas escribió los números entre comillas («"-0.15"») tras el aviso de la
     pareja; al intento siguiente lo corrigió. En T14 por fases repitió la misma respuesta (81/82, el pie no
     adelantado) en los intentos 2 y 3: ignoró el aviso una vez.
   - Inventó `centro_z(Cabeza)` (avisado: no existe) y una vez puso z(Cabeza) en la y; los dos corregidos al momento.
   - Segundos por respuesta: 6–68 s (media ≈ 30 s); qwen25 y ministral3, ~6–23 s.
**Sesgo conocido (anotado, sin cambiar nada):** el resolvedor exige números sin comillas; aceptar «"-0.15"» como número
le habría ahorrado 3 intentos a gemma12. Se propone como mejora general, con su propia comprobación.
