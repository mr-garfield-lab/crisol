# Interfaces para los módulos de Codex (V2-F.1)

Codex desarrolla tres módulos complementarios: **recuperación de memoria**, **selección de herramientas** y **diagnóstico de errores**. V2-F.1 no los implementa ni los duplica. Define:

1. el **contrato** de cada uno;
2. un **adaptador por defecto** sobre lo que ya existe en V2-F, para que el sistema funcione hoy sin esperar a Codex;
3. una **capa de validación** por la que pasa toda salida, venga del adaptador por defecto o de Codex.

Código: `src/eq2/interfaces_codex.py` (versión de interfaz `eq2-codex-1`). Pruebas: `tests/test_v2f1_codex.py`.

## Contratos

Cada componente es un objeto con un atributo `nombre` (texto) y un método.

| Componente | Método | Entrada | Salida |
|---|---|---|---|
| Recuperador de memoria | `recuperar(agente, consulta, n)` | `"A1"`/`"A2"`/`"A3"`, texto, entero | lista de `{"texto", "tipo", "fuente", "estado"}` (opcionales: `id`, `fecha`, `confianza`, `tarea_ref`) |
| Selector de herramientas | `seleccionar(necesidad, contexto)` | `comprobar_sintaxis` / `comprobar_comportamiento` / `ejecutar_casos`; `{"agente", "flujo", "autorizado", "ejecucion_dinamica", "candidatas"}` | `{"herramienta": <nombre del registro>, "motivo": texto}` |
| Diagnóstico de errores | `diagnosticar(errores, archivos)` | hechos del controlador `{"tipo", "archivo", "linea", "detalle", "nombre", "modulo"}`; `{ruta: código}` | lista de `{"causa", "archivo", "linea", "propuesta", "confianza"}` |

Valores admitidos:
- `tipo`: `hecho`, `hipotesis`, `leccion`, `criterio` (los de `aprendizaje.TIPOS`).
- `fuente`: los de `aprendizaje.FUENTES`.
- `estado`: `hipotesis`, `sin_verificar` o `verificada_por_prueba`. Lo refutado o supersedido no se admite.
- `confianza`: `baja`, `media` o `alta`.

## Qué valida el controlador (siempre)

- **Lo inválido se descarta y se registra** en `componentes.incidencias` del informe. Nunca se corrige en silencio.
- **Recuerdos:**
  - como máximo 5, de 300 caracteres;
  - cada texto pasa por `aprendizaje.analizar_contenido`: lo instructivo o en cuarentena se descarta;
  - en el prompt van marcados `origen=externo:<nombre>` bajo el aviso de DATOS NO CONFIABLES.
- **Herramientas:** la elección se acepta solo si se cumplen todas estas condiciones:
  - existe en `herramientas.REGISTRO`;
  - sirve para esa necesidad;
  - la puede usar ese agente en ese flujo;
  - tiene la autorización que exige;
  - **no ejecuta código** cuando la ejecución dinámica está bloqueada (siempre, en la función supervisada).

  Si no, se usa la elección determinista por defecto. Las claves extra de la salida (`"autorizado"`, `"permisos"`…) se ignoran.
- **Diagnósticos:**
  - como máximo 6;
  - el archivo citado debe existir y la línea, estar dentro de él;
  - la confianza debe ser una de las admitidas;
  - el contenido pasa el mismo filtro que los recuerdos.

  Son **hipótesis** para el prompt de A1: no cambian el flujo ni el veredicto, y el controlador vuelve a analizar la versión corregida.
- **Sin objetos con poder.** Los componentes reciben solo textos, enteros, listas y diccionarios copiados: nunca el laboratorio, el backend, el despachador ni la configuración. Una prueba lo comprueba.
- **Un componente que falla no detiene la tarea.** Si lanza una excepción, se usa el adaptador por defecto (`origen = por_defecto_tras_fallo`) y queda registrado.

## Adaptadores por defecto (sin duplicar a Codex)

| Componente | Adaptador | Se apoya en |
|---|---|---|
| Recuperador | `RecuperadorExperiencias` | `experiencias.MemoriaEquipo`: bases individuales `aprendizaje/a1.db`, `a2.db`, `a3.db` |
| Selector | `SelectorRegistro` | `herramientas.seleccionar`: tabla determinista con sustitución por análisis estático |
| Diagnóstico | `DiagnosticoEstatico` | `autocorreccion.diagnostico_estatico` para los cuatro tipos de V2-F, más una propuesta por tipo de bloqueo |

## Cómo conectar un módulo de Codex

No hay carga dinámica de módulos: el validador estático prohíbe `importlib`. Se conecta por código:

```python
from eq2 import interfaces_codex, tareas, funcion_supervisada

mi = MiRecuperadorCodex()                      # objeto con .nombre y .recuperar(agente, consulta, n)
assert interfaces_codex.comprobar_conformidad(mi, "recuperador") == []
ts = tareas.Tareas()
ts.ejecutar("LAB-001", agentes, backend=be, componentes_codex={"recuperador": mi})
```

`comprobar_conformidad(obj, componente)`:
- comprueba el nombre, el método y su aridad;
- hace UNA llamada de sonda y valida la salida con las mismas reglas que en uso;
- devuelve la lista de problemas (vacía = conforme).

Hoy `componentes_codex` solo lo usan las tareas `funcion_supervisada`.

## Lo que queda para Codex

- La calidad de la recuperación (relevancia, consolidación).
- La selección cuando haya más herramientas.
- Diagnósticos mejores que la tabla fija.

Las interfaces no fijan cómo se hace. Fijan qué entra, qué sale y qué no puede hacer.
