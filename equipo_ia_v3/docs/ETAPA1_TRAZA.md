# Equipo IA V3 — Etapa 1: núcleo, trazabilidad y calidad

**Estado: CERRADA** (2026-11-10). La puerta se superó: F0–F5 correctas (`evidencias/etapa1/`).

## 1. Qué aporta

Una **traza unificada y verificable** de cada ejecución de A1, A2 y A3. Antes, esa información estaba repartida
entre varios JSONL por ejecución y una base SQLite por agente (Etapa 0, §9).

```
objetivo → análisis → agentes → decisiones → autorización → acciones → cambios → pruebas → resultado → experiencias
```

`sistema/` (V2-F.1) **no se modifica**. La capa V3 (`eq3/`) usa eq2 como biblioteca (las tarjetas de rol de
`roles.py`) e importa lo que eq2 ya escribe en su laboratorio. Así, la puerta de regresión de la Etapa 0 sigue
midiendo la base sin cambios.

| Componente | Función |
|---|---|
| `eq3/traza.py` | Base SQLite con 11 tablas enlazadas por claves foráneas y restricciones CHECK. Solo admite añadir (disparadores contra UPDATE y DELETE) y guarda una cadena de hashes SHA-256 en `registro` |
| `eq3/ingesta.py` | Importa ejecuciones de tareas `funcion_supervisada` tratando todo como datos no confiables: confinamiento de rutas, enlaces simbólicos rechazados en cada componente, límites de tamaño y de anidamiento, SHA-256 declarados comprobados contra los archivos, una transacción por ejecución y STOP seguro |
| `eq3/reconstruccion.py` | `reconstruir()` devuelve la cadena completa; `verificar()` comprueba la cadena de hashes, el contenido de cada tabla, el hash de cada archivo y recuerdo referenciado y las reglas R1–R6 |
| `eq3/registro.py` | Registro estructurado JSON Lines: solo identificadores, recuentos y motivos, nunca textos de agentes |
| `equipo3.py` | Orden `traza importar | listar | reconstruir [--json] | verificar` |
| `verificar_v3.py` | Verificador integral de V3 (fases F0–F5) |
| `v3/mutacion.py` | Herramienta reutilizable de pruebas de mutación (control obligatorio y espejo temporal) |

### Correspondencia con la orden maestra

| Requisito | Cómo se cumple |
|---|---|
| Identidad de los agentes | Tabla `agentes`: rol, SHA-256 de su tarjeta de rol, backend y naturaleza (SIMULADA, REAL o DETERMINISTA) |
| Registros estructurados | `registro_v3.jsonl` |
| Trazabilidad de tareas y cambios | Cada versión de la solución guarda el SHA-256 de antes y de después y su diff, enlazada con la anterior (regla R2) |
| Validación | Ingesta estricta (§3) |
| Revisión de calidad | Análisis estático por versión enlazado (`analisis`) y pruebas de mutación |
| Gestión de errores | Excepciones tipadas y códigos 0/1/2/3 |
| STOP seguro | `<lab>/STOP` o `<lab>/tareas/<id>/STOP`; la transacción se deshace entera |
| Control de versiones | Las versiones de la solución en la traza; los puntos de recuperación en Git (commits locales) |

## 2. Uso (desde `equipo_ia_v3/`)

```sh
cd sistema && python3 -B equipo.py demo funcion && cd ..        # una ejecución de V2-F.1 (SIMULADA)
python3 -B equipo3.py traza importar LAB-001
python3 -B equipo3.py traza reconstruir LAB-001/E001            # o --json
python3 -B equipo3.py traza verificar LAB-001/E001              # 0 correcta · 1 problemas
python3 -B verificar_v3.py [--completo]                         # verificador integral
```

Salida real de `reconstruir` (resumen):

- **Agentes:** A1 programador, A2 analista y A3 revisor crítico, todos [SIMULADA], más el controlador
  [DETERMINISTA].
- **Acciones:** 7 pasos de agente, cada uno con el SHA-256 de su respuesta y de su prompt, y 3 llamadas a
  herramientas.
- **Decisiones y autorización:** 23 decisiones; la autorización `pruebas_python` NO se concedió.
- **Cambios:** v1 `—→a5943d`, v2 `a5943d→4f82dc` y v3 `4f82dc→76751b`.
- **Pruebas:** 6 pendientes, sin ejecutar.
- **Resultado y experiencias:** completada / `aceptada_sin_ejecucion` (versión 3); 12 experiencias.

## 3. Garantías comprobadas

- **Manipulación detectada:**
  - una respuesta de agente modificada;
  - una versión de la solución modificada;
  - una fila alterada tras quitar los disparadores (además, R6 detecta un «verificado» sin autorización);
  - la cadena de hashes alterada;
  - una fila insertada fuera de la cadena;
  - un recuerdo de aprendizaje cambiado.
- **La base impide modificar y borrar:** UPDATE y DELETE fallan en todas las tablas, incluido `registro`.
- **Ingesta segura:**
  - rechaza rutas con `..` y separadores `\`, y enlaces simbólicos a archivos y a CARPETAS (lo segundo solo lo
    detiene la comprobación componente a componente);
  - rechaza hashes declarados falsos, JSON malformado, tipos inválidos y anidamiento extremo (unos 400 KB de
    `[[[…]]]`);
  - rechaza los tipos de tarea no soportados.

  En todos estos casos no queda ninguna fila parcial.
- **Texto de agente como dato:** una respuesta con forma de SQL o de instrucción («IGNORA LAS INSTRUCCIONES»)
  se guarda solo por su hash y no altera nada.
- **STOP:** antes de empezar y a mitad de la inserción, deshace la transacción entera (0 filas en las 11
  tablas), y la importación se puede reanudar después.
- **Otras propiedades:** reimportar no duplica; una ejecución SIMULADA nunca figura como REAL (R5); una base de
  trazas dañada da un error controlado (código 2), sin excepción sin capturar.

## 4. Pruebas y resultados

| Prueba | Resultado |
|---|---|
| `pruebas/test_eq3_traza.py` | 23 de 23 correctas |
| Mutación de la Etapa 1 (`v3/mutaciones/etapa1.json`) | 12 de 12 detectadas |
| Verificador integral `verificar_v3.py --completo` | F0–F5 correctas tras dos correcciones documentadas en §4.5 y en `evidencias/etapa1/LEEME.md`: F5 IGUAL 503 de 503 y mutaciones 6/6 y 12/12 |

**Hallazgos durante la etapa** (corregidos, sin rebajar ningún criterio):

1. **Formatos reales de eq2:** `ejecucion_dinamica` y `version_recomendada` eran objetos, no los valores que
   supuse. Ahora también se comprueban los hashes de `solucion_final/`.
2. **Estructura de `casos.json`:** contiene grupos con formatos distintos (`usados`, `excluidos`…). Los «usados»
   pasan a ser pruebas pendientes, y el archivo entero queda enlazado por su hash.
3. **Pruebas débiles de rutas y enlaces:** las mutaciones M2 y M3 sobrevivieron porque las pruebas apuntaban a
   `/etc/hostname`, que no existe en este contenedor (se rechazaba por «no existe», no por la protección). Ahora
   apuntan a un archivo REAL de fuera del laboratorio con su hash correcto y comprueban el motivo exacto.
4. **Excepciones sin capturar:** `RecursionError` en JSON anidado y `sqlite3.Error` en la CLI. Ahora se
   capturan y tienen sus mutaciones M11 y M12.
5. **Defecto en la herramienta de la Etapa 0, encontrado por la propia puerta.** La primera ejecución de
   `verificar_v3.py --completo` dio F5 FALLO, con 5 CAMBIO en Contexto Ligero
   (`evidencias/etapa1/verificacion_1_fallida_firma/`).
   - **Causa:** el corredor recortaba cada mensaje a 240 caracteres ANTES de sustituir las rutas temporales,
     así que la firma dependía de la LONGITUD de la carpeta de salida, y la del verificador integral es más
     profunda.
   - **Corrección:** se normaliza primero y se recorta después (`MAX_LINEA_CRUDA`).
   - **Cobertura:** la prueba de firmas estables usa ahora carpetas de longitud muy distinta, y la mutación M6 de
     la Etapa 0 reproduce el defecto y queda detectada.
   - **Línea base:** NO cambia. Desde una carpeta extremadamente profunda, codex y contexto dan IGUAL 239 de 239
     con la línea base existente, cuyas firmas ya eran completas. La puerta falló hacia el lado seguro: informó
     CAMBIO, no ocultó nada.

## 5. Criterios de aceptación de la Etapa 1

| Criterio | Evidencia | Cumple |
|---|---|---|
| Reconstrucción verificable de las acciones | `reconstruir` y `verificar` sobre ejecuciones reales de V2-F.1 (dos flujos); manipulaciones detectadas | Sí |
| Pruebas de seguridad superadas | `TestIngestaSegura`, `TestManipulacion`, `TestStop`; mutaciones M1–M12 | Sí |
| Pruebas de regresión superadas | F0: sistema/ sin cambios. F5: la línea base da IGUAL 503 de 503 | Sí |
| Sin código innecesario ni duplicado | Revisión de §6 | Sí |

## 6. Revisión de calidad y deuda técnica

- **Tamaño:** `eq3/` tiene 4 módulos. Las funciones largas son las de lectura de cada tipo de registro
  (`leer_ejecucion`), que conviene dividir si se añaden tipos de tarea.
- **Lecturas dobles eliminadas:** `existe()` ya no lee los archivos; valida con `ruta_segura`.
- **Sin duplicación con eq2:** los roles salen de `eq2.roles`. Las bases de aprendizaje se leen, nunca se
  reescriben.
- **SQL:** los nombres de tablas y columnas solo proceden de listas blancas internas, y todos los valores van
  parametrizados.

## 7. Limitaciones (no se declaran resueltas)

1. **Ingesta posterior:** la traza se construye DESPUÉS de cada ejecución, a partir de sus archivos; eq2 todavía
   no la emite en vivo.
2. **Tipos de tarea:** solo `funcion_supervisada`. Los demás tipos (p. ej. `modlab_pz`) se rechazan con
   `NoSoportado`.
3. **Ejecución dinámica:** solo se importan ejecuciones con la ejecución dinámica bloqueada, que hoy es la única
   posibilidad (SEG-01).
4. **Tarjeta de rol:** su hash se calcula con la tarjeta de rol vigente al importar; eq2 no registra en la
   ejecución la que usó.
5. **Autorización:** se deriva de la bandera `--autorizo-pruebas`. El registro completo de propuesta →
   autorización → ejecución (actor, alcance, caducidad) se hará en la Etapa 3, cuando exista una acción que
   autorizar (aplicar cambios).
6. **Archivos no copiados:** la traza no copia los textos (privacidad y tamaño). Si se borran del laboratorio,
   `verificar` lo informa como problema.
7. **Plataformas:** no validado en Android/Termux ni en Windows. Usa SQLite estándar (disparadores, claves
   foráneas, CHECK), disponible en el Python de Termux.
