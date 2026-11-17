# Equipo IA V3 — Etapa 4: debate, planificación y coordinación

**Estado: CERRADA** (2026-11-10). `verificar_v3.py --completo` da F0–F8 correctas (`evidencias/etapa4/`).

## 1. Punto de partida

V2-F.1 ya tiene un debate por evidencias entre A1, A2 y A3:
- **Decisión:** determinista, sin votos (`debate.py`, `protocolo.py`, `criticas.py`).
- **Plan:** estructurado (`planificacion.py`), con objeciones abiertas y cerradas registradas.
- **Roles:** tarjetas con criterios y prohibiciones (`roles.py`).

No había nada que comprobara si las EVIDENCIAS que citan los agentes existen de verdad. El rol de A2 prohíbe
«citar líneas que no existen», pero nadie lo verificaba. Esta etapa no reimplementa el debate: le añade esa
comprobación y un informe de calidad de la deliberación sobre la traza.

## 2. Qué aporta

`eq3/citas.py` es determinista, solo lee y nunca ejecuta.

| Cita reconocida | Se comprueba que… |
|---|---|
| `línea N`, `líneas N-M` (protocolo de V2-F.1: `EVIDENCIA: línea 4`) | existen en la versión de la solución que el agente tenía delante y, si se cita código entre comillas invertidas, que aparece en esas líneas |
| `caso ID` | figura en los casos registrados (usados o excluidos) |
| `EVn` | es uno de los hechos del controlador (EV1…EV7) |
| `ruta.py:N`, `ruta.py:N-M`, `ruta.py::símbolo` (también `Clase.método`) | el archivo existe dentro de la raíz, sin «..», sin rutas absolutas ni enlaces; las líneas existen; el símbolo está definido según `ast` |

Una cita sin base con la que contrastarla da `sin_base` y **nunca** cuenta como verificada. Una cita con `../`
o con una ruta absoluta se informa como `ruta_no_permitida`; no se ignora en silencio.

`deliberacion(traza, lab, ejecución)` genera el informe de calidad:

- **Por agente:** citas verificadas, inválidas y sin base, y afirmaciones sin evidencia (las que registra
  V2-F.1).
- **Objeciones:** abiertas y cerradas.
- **Por paso:** la versión que se usó realmente para contrastar.
- **Textos alterados:** un texto de agente cuyo SHA-256 ya no coincide con la traza no se analiza como
  auténtico; se lista en `alterados`.

Resultado sobre una ejecución real de V2-F.1 (agentes SIMULADOS):

- todas las citas de A1, A2 y A3 quedan verificadas, y no hay inválidas;
- la versión visible por paso es [—, 1, 1, 1, 2, 3, 3];
- hay 6 objeciones, de las que 5 se cerraron y 1 sigue abierta.

## 3. Pruebas

| Prueba | Resultado |
|---|---|
| `pruebas/test_eq3_citas.py` | 10 de 10 correctas, incluida la orden `equipo3.py traza deliberacion`, que da código 1 ante un texto alterado |
| Mutación de la Etapa 4 (`v3/mutaciones/etapa4.json`) | 10 de 10 detectadas |
| Verificador integral | F0–F8 correctas; F7 = mutación de la Etapa 4, 10 de 10 |

Hallazgos durante la etapa, todos corregidos y cubiertos por una mutación:

1. **Cortar frases en cada punto rompía `x.py`**, y se perdían las citas de código (M10).
2. **Las citas con `../` o con ruta absoluta se ignoraban en silencio** en lugar de rechazarse (M9).
3. **El informe calculaba la versión visible en lugar de informar la versión realmente usada** para
   contrastar. Con un error de mapeo, el informe habría seguido pareciendo correcto (M6, que sobrevivió hasta
   la corrección).

## 4. Limitaciones

1. **Solo existencia, no razón.** El verificador comprueba que lo citado EXISTE y, si se cita texto, que
   coincide. No juzga si el argumento es correcto: eso sigue siendo del debate y de las pruebas, y las pruebas
   no pueden ejecutarse (SEG-01).
2. **Mapeo paso → versión.** El número de pasos `fs_generar`/`fs_corregir` anteriores sigue el protocolo de la
   función supervisada de V2-F.1; para otros flujos habría que declararlo.
3. **Agentes simulados.** Con agentes SIMULADOS las citas son correctas por construcción del guion. El valor real
   aparece con Qwen, que puede inventar líneas; no se ha probado aquí.
4. **Sin contexto del grafo para los agentes.** Que A1/A2 reciban paquetes de contexto del grafo (Etapa 2) durante
   la tarea exige tocar los prompts de V2-F.1. No se ha hecho, para no modificar `sistema/`; queda como trabajo
   futuro, con su propia línea base.
