# Equipo IA V3 — Etapa 3: programación autónoma controlada

**Estado: CERRADA** (2026-11-10). `verificar_v3.py --completo` da F0–F7 correctas (`evidencias/etapa2_3/`).

## 1. Qué aporta

Los agentes ya pueden trabajar sobre **proyectos Python reales** del laboratorio
(`<lab>/proyectos_v3/<proyecto>/`) con la separación estricta que exige la orden maestra. El núcleo es
`eq3/cambios.py`, que se apoya en `eq3/almacen.py` (solo añadir, cadena de hashes) y reutiliza el análisis
estático de V2-F.1.

```
agente: proponer ──► usuario: autorizar ──► controlador: aplicar
  (sin escribir)       (CLI, hash tecleado)    (atómico, contra el TOCTOU, registrado)
```

| Garantía | Cómo |
|---|---|
| Herramientas tipadas | `REGISTRO` congelado (`MappingProxyType` de dataclasses inmutables) con `leer`, `listar`, `buscar`, `proponer` y `ejecutar_pruebas`. Cada argumento declara su tipo y su longitud máxima; `huella_registro()` |
| Ningún agente escribe, autoriza ni ejecuta | El registro no contiene esas operaciones, así que una solicitud de `aplicar`, `autorizar` o `escribir` da `herramienta_desconocida`. A3 no puede proponer |
| Ejecución arbitraria prohibida | `ejecutar_pruebas` devuelve siempre `no_disponible` (SEG-01). El código propuesto solo se analiza con `ast.parse`; nunca se importa ni se ejecuta |
| Autorización del usuario | Se teclean ≥ 12 caracteres del SHA-256 del contenido propuesto. Es de un solo uso (`UNIQUE`), caduca (1 min – 24 h), exige `actor = 'usuario'` (CHECK) y vale solo para esa propuesta |
| Revisión antes de autorizar | Análisis estático de V2-F.1: una propuesta con errores de sintaxis no se puede autorizar, y los avisos de riesgo (`os`, `subprocess`, `eval`…) exigen `acepto_avisos` |
| Aplicación segura | Primero se comprueba que el archivo siga con el SHA-256 de la propuesta (TOCTOU). Luego se escribe de forma atómica (temporal + `os.replace`) y se verifica el resultado. Las rutas tienen dos capas de confinamiento, y los enlaces simbólicos se rechazan en cualquier tramo |
| Trazabilidad | Propuestas (diff, análisis, origen), autorizaciones, aplicaciones y CADA rechazo, en `cambios_v3.sqlite3` (solo añadir, cadena de hashes). `verificar()` también detecta los archivos modificados FUERA del flujo |
| Integración con las etapas 1 y 2 | `proponer_desde_traza()` lleva la versión recomendada de una ejecución de A1/A2/A3 a un proyecto, comprobando su SHA-256 contra la traza. `buscar` usa el índice de Contexto Ligero sobre el proyecto |

## 2. Demostración (ejecución real de V2-F.1 con agentes SIMULADOS)

1. `equipo.py demo funcion`: A1, A2 y A3 producen v1→v2→v3 de `mediana`.
2. La traza importa la ejecución (Etapa 1).
3. `proponer_desde_traza` crea `PROP-0001` (A1, origen `traza:LAB-001/E001:v3`), con el mismo SHA-256 que la
   v3 de la traza (`76751bc4…`).
4. Intentos rechazados: aplicar sin autorizar y autorizar con un SHA incorrecto.
5. Se autoriza, se aplica y `verificar()` da CORRECTO.
6. Una segunda aplicación se rechaza por ser de un solo uso.

## 3. Pruebas

| Prueba | Resultado |
|---|---|
| `pruebas/test_eq3_cambios.py` | 12 de 12 correctas |
| Mutación de la Etapa 3 (`v3/mutaciones/etapa3.json`) | 12 de 12 detectadas |
| Verificador integral | F0–F7 correctas; F6 = mutación de la Etapa 3, 12 de 12 |

Mutaciones detectadas:

- aplicar sin autorización;
- sin control TOCTOU;
- autorización reutilizable;
- caducidad ignorada;
- confirmación débil;
- avisos sin aceptar;
- herramienta de escritura para los agentes;
- pruebas presentadas como ejecutadas;
- código con errores de sintaxis autorizable;
- cambios fuera del flujo ignorados;
- traza sin comprobar el hash;
- rutas sin confinar en la primera capa.

## 4. Limitaciones

1. **Sin ejecución de pruebas.** No se ejecuta ninguna prueba del código generado mientras no haya un
   aislamiento del sistema operativo verificable. En Termux sin root no lo hay. Lo aplicado está «aceptado sin
   ejecución», nunca «verificado».
2. **Solo Python.** Únicamente archivos `.py` y, por propuesta, el contenido completo de un archivo (no parches
   parciales).
3. **Autorización local.** Se da por la CLI de la máquina del usuario; no hay autenticación de usuarios
   distintos.
4. **Agentes simulados.** Las propuestas de esta etapa se probaron con agentes SIMULADOS y con contenido de la
   traza. Con Qwen real, el flujo es el mismo, pero no se ha ejecutado aquí.
