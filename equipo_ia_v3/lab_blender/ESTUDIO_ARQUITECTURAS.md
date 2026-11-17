# Estudio: arquitecturas para que cerebros pequeños construyan en 3D

Fecha: 2026-11-15. Motivo: en las tandas 9–11 los cerebros entienden la estructura del robot pero fallan al combinar
medidas (qwen25 oscila entre tamaño y altura; ministral3 solo acierta cuando el número le llega hecho o tiene datos
limpios delante).

## Qué dice la literatura (fuentes al final)
1. **Coordenadas directas del modelo (LayoutGPT).** El LLM escribe las posiciones numéricas. Los trabajos posteriores
   le reprochan choques y piezas fuera de sitio. Es lo que hacemos hoy con bpy suelto.
2. **Relaciones + resolvedor (Holodeck, Holodeck 2.0).** El LLM elige relaciones («delante de», «contra la pared») y
   un resolvedor sin IA (búsqueda en profundidad o programación lineal entera) calcula las posiciones. Holodeck 2.0 hace
   que el LLM escriba las restricciones en JSON y el resolvedor dice qué objeto no pudo colocar.
3. **Grafo de escena → código Blender + biblioteca de funciones (SceneCraft).** Un planificador hace el grafo de
   relaciones, otro paso lo traduce a un script de Blender, se renderiza y se revisa; con el tiempo junta una
   biblioteca de funciones reutilizables.
4. **Lenguaje propio con resolvedor geométrico (AIDL; aDSL).** AIDL descarga el razonamiento espacial en un
   resolvedor de restricciones y el LLM solo planifica la estructura; en sus pruebas supera a OpenSCAD. aDSL añade
   operadores declarativos (colocar, alinear centros) para que una relación sea UNA instrucción y no una cuenta frágil.
5. **Mejorar el modelo por dentro (CAD-GPT, sobre un 7B).** Entrenamiento específico; fuera de nuestro alcance (no
   entrenamos cerebros).
6. **Optimización diferenciable (LayoutVLM, RoboLayout).** Para escenas grandes con muchas restricciones blandas;
   excesivo para robots de 6 piezas.

Coincidencia general: **el modelo dice QUÉ (piezas, tamaños, relaciones) y un programa calcula el CUÁNTO.** Es el
mismo patrón que ya nos funcionó con javac en el banco de revisión (de 10/24 a 23/23).

Límite de la búsqueda: no encontré estudios que midan esto con modelos de 7–8B en local; casi todos usan modelos
grandes. Por eso hay que medirlo nosotros.

## Propuesta: tanda 12, dos arquitecturas frente a las tandas 9–11
Mismas tareas (T05, T08), mismos cerebros, mismo verificador de Blender con TODAS las comprobaciones originales.

**A · Funciones de alto nivel (estilo aDSL/SceneCraft).** El cerebro sigue escribiendo Python, pero con una pequeña
biblioteca ya cargada: `caja(nombre, medidas, padre)`, `encima(a, b)`, `debajo(a, b)`, `a_la_izquierda(a, b)`,
`a_la_derecha(a, b)`, `en_el_suelo(a)`, `centrar_xy(a, b)`, `avanzar(objeto, desplazamiento, f0, f1)`. Cada función
hace la cuenta exacta. Cambio mínimo; el cerebro ya sabe Python.

**B · JSON + resolvedor (estilo Holodeck 2.0/AIDL).** El cerebro solo escribe un JSON con piezas (medidas, padre) y
relaciones. Un resolvedor nuestro, sin IA, coloca las piezas recorriendo el árbol desde la raíz, comprueba que no haya
relaciones en conflicto y genera el script de Blender. Si el JSON está mal o hay conflicto, se le dice exactamente
qué relación falla (como Holodeck 2.0). No hace falta un resolvedor tipo MILP: los robots son árboles.

Las dos se prueban **de una vez** (todo el robot en un turno; el JSON cabe de sobra en 800 tokens) y, si hace falta,
por pasos. Antes, cerebro falso en Blender real y preregistro con reglas fijadas.

Qué mide de verdad: si el cerebro elige bien piezas, medidas y relaciones. La geometría la garantiza el programa. Es
justo el reparto que queremos comprobar.

## Fuentes
- Holodeck: https://arxiv.org/pdf/2312.09067
- Holodeck 2.0: https://arxiv.org/pdf/2508.05899
- SceneCraft: https://proceedings.mlr.press/v235/hu24g.html
- AIDL (lenguaje con resolvedor para CAD): https://arxiv.org/pdf/2502.09819
- aDSL: https://arxiv.org/pdf/2608.17975
- CAD-GPT: https://arxiv.org/pdf/2412.19663
- RoboLayout: https://arxiv.org/html/2603.05522
- R³L: https://arxiv.org/pdf/2605.06758
