# Equipo IA V3.1 — paquete de pruebas (2026-11-15)

Sistema experimental de agentes de IA **locales** (sin APIs de pago ni conexión a servicios externos), con los bancos
de pruebas que miden de verdad qué hace bien y qué no. Todo se mide con **verificadores sin IA** (respuesta exacta
conocida) y con **reglas de decisión fijadas antes de ver los resultados** (prerregistros).

**Para empezar: `equipo_ia_v3/GUIA_AMIGO_BANCOS.md`** (paso a paso, con Docker y con Windows).

## Qué hay dentro

| Carpeta | Qué es |
|---|---|
| `equipo_ia_v3/sistema/` | Equipo IA: el núcleo con los agentes A1, A2 y A3 sobre modelos locales (llama.cpp) |
| `equipo_ia_v3/lab_flujos/` | **Banco de flujos grandes**: proyectos 65–90 veces mayores que el contexto del modelo |
| `equipo_ia_v3/lab_revision/` | **Banco de revisión de código**: encontrar y arreglar errores en Python y Java |
| `equipo_ia_v3/lab_blender/` | **Banco de Blender**: el modelo escribe scripts y un verificador mide la escena |
| `fuentes/contexto_ligero_v35/` | **Contexto Ligero**: el buscador de código que alimenta a los modelos (Python y Java) |
| `equipo_ia_v3/evidencias/` | Resultados del PC de origen de los bancos de flujos, revisión y Blender, para comparar |

Cada banco tiene sus `PRERREGISTRO_*.md` con la pregunta, el montaje, las reglas y el resultado.

## Resultados principales (PC de origen: RTX 3050 8 GB, cerebros qwen25 y ministral3)

**Leer proyectos grandes** (tanda 7, código real de Equipo IA, preguntas como las haría una persona):

| | Solo búsqueda (Contexto Ligero) | Búsqueda y, si no encuentra, identidad |
|---|---|---|
| qwen25 | 16/24 | **21/24** |
| ministral3 | 16/24 | **22/24** |

Sin búsqueda, en un proyecto que no cabe, aciertan 0. Las tareas cortadas a medias se reanudan sin repetir ni perder
trabajo (comprobado con paradas reales).

**Revisar y arreglar código** (24 archivos con error y 8 correctos, Python y Java):

| | El modelo solo | Con compilador en el bucle y las mejoras |
|---|---|---|
| qwen25 | 10/24 | **23/24** |
| ministral3 | 10/24 | **23/24** |

Con el compilador delante: ningún archivo correcto roto, ninguna falsa alarma, ningún arreglo que toque de más.

## Lo más importante que se aprendió

- **La herramienta comprueba y el modelo explica.** Un compilador o un buscador hacen lo exacto; el modelo, lo que
  requiere lenguaje. Solos, los modelos pequeños fallan la mitad o ven errores donde no los hay.
- **Los modelos casi nunca inventan números de la nada; confunden de qué función se habla.** Por eso se cita siempre
  la fuente y se comprueba que el dato está escrito en ella.
- **Nada se da por bueno a medias**: el trabajo largo se trocea con puntos de guardado.

## No incluye
Modelos (≈5 GB cada uno), llama.cpp, Blender, JDK, bases de datos, contraseñas ni datos personales: el empaquetador
rechaza el paquete si encuentra credenciales, correos, rutas personales o identificadores del dueño, y deja fuera los
archivos que no puede revisar (imágenes, vídeos, registros binarios). Las rutas de la máquina de origen aparecen como
`<TRABAJO>` y `<CASA>`. Enlaces oficiales y huellas SHA-256 de lo que hay que descargar: en la guía.

## Límites honestos
Sistema experimental, no listo para producción. Modelos de 7–8B en una GPU de 8 GB. Validado en Windows 11; la
verificación sin GPU también en Docker (Linux). Sin probar en Android/Termux. Contexto Ligero lee Java sin compilador
(no resuelve tipos ni herencia). Los bancos no miden todavía código malicioso ni errores de lógica.
