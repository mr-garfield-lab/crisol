# Equipo IA V3.1 — Etapa corta de mantenimiento antes de F1 (2026-11-11)

**Autorizada por el usuario** tras el cierre de F0.5, con cuatro prioridades y sin implementar otras mejoras.
`sistema/` sin modificar, sin ejecutar código generado por agentes, sin APIs de pago. Única instalación: Git
(autorizada expresamente).

## 1. Resultado

| # | Prioridad | Resultado | Commit (rama `mantenimiento-v31`) |
|---|---|---|---|
| 1 | Reanudación del verificador (`--reanudar`) | **Hecha**: huella de código y entorno; nada obsoleto se reutiliza | `06db07d` |
| 2 | Rechazo de rutas personales en el empaquetador | **Hecho**, con anonimización solo en registros y documentación | `76e156e`, `4298331` |
| 3 | Git exclusivamente local | **Hecho**: sin remotos, guardia anti-`push`, bytes exactos | `60c5fbd` (base), `42072b0` |
| 4 | Criterio de `majflt` en Windows | **Investigado y propuesto** (no implementado): `docs/V31_MAJFLT_WINDOWS.md` | `42072b0` |

## 1.1 Validación integral

**Resultado final: 15 de 15 fases correctas en una ejecución completa, sin reanudar**, sobre el código definitivo
(commit `4298331`). Lo que pasó hasta llegar ahí, sin maquillar:

| Intento | Código | Ejecución | Resultado |
|---|---|---|---|
| 1 | `42072b0` | `20261111T082749_589751Z`, completa (2493 s) | **14/15: F11 FALLÓ** por un único cambio, **V-CON-11** (de 2 a 4 subpruebas fallidas) |
| 2 | `42072b0` | `20261111T091325_759865Z`, `--reanudar` del intento 1 (980 s) | 15/15; F11 503 IGUAL. Reutilizó 13 fases (código y entorno idénticos, 745 archivos), repitió F0 y F11 |
| — | — | Comprobación del ZIP generado | **Fuga encontrada** (§3): se corrige el empaquetador (`4298331`), se descarta ese ZIP |
| **3** | **`4298331`** | **`20261111T094925_820054Z`, completa (2575 s)** | **15/15, ESTADO GENERAL: CORRECTO**: F14 12/12, F11 503 IGUAL, idéntica prueba a prueba al cierre de F0.5 |

**Causa del fallo del intento 1, demostrada:** V-CON-11 contiene una subprueba de V2-F.1 que compara dos lecturas
seguidas de la memoria disponible; con memoria real de Windows a veces difieren unos kB (1 fallo en 30 ejecuciones
aisladas: `evidencias/v31_mantenimiento/V-CON-11_inestabilidad_30_ejecuciones.md`). No es una regresión del
mantenimiento: `git diff --name-only 60c5fbd 42072b0 -- equipo_ia_v3/sistema equipo_ia_v3/eq3 fuentes` = 0
archivos. **Es un defecto ABIERTO**, que ya existía desde F0.5 sin haberse manifestado, y no se ha ocultado: la
línea base no cambió. El segundo intento pasó porque esta vez las dos lecturas coincidieron, no porque se arreglara
nada. Propuesta: experimento X1 de `docs/V32_ESTUDIO_DEBATE.md`.

El intento 2 es también la **primera reanudación real**: hizo exactamente lo diseñado (comprobó la huella, reutilizó
solo las fases correctas y anotó `reutilizada_de` en cada una).

Después de la validación final (intento 3) solo cambiaron documentación y evidencias (`docs/`, `evidencias/`,
`PROGRESO.md`): comprobable con `git diff --stat 4298331` sobre el commit final.

## 2. Reanudación del verificador

`python -B verificar_v3.py [--completo] --reanudar <carpeta de una ejecución anterior>`

- Cada ejecución guarda `progreso.json` tras cada fase (escritura atómica), con su **huella**:
  - el SHA-256 de **cada archivo** del árbol: `equipo_ia_v3/`, `fuentes/` y los sueltos, sin `.git` ni cachés;
  - el **entorno**: versión y ejecutable de Python, sistema, entorno exacto de los procesos hijo, carpeta temporal y
    capacidad de crear symlinks (que decide qué pruebas se omiten).
- **Se reutiliza solo si la huella es idéntica**, archivo por archivo; si no, código 2, se lista qué cambió y no se
  ejecuta nada. Manipular el resumen guardado no sirve (prueba dedicada).
- Solo se reutilizan fases **OK con la misma orden**; las fallidas, las no terminadas y F0 se ejecutan de nuevo.
- **Cambio durante la ejecución:** la huella se recalcula al terminar; si difiere, fallo `HUELLA`, el resultado no
  vale y esa ejecución queda marcada como inválida (no se puede reanudar ni aunque el archivo vuelva a su estado).
- Cada fase reutilizada figura en el informe con `reutilizada_de` (la ejecución que la ejecutó de verdad, también a
  través de varias reanudaciones).
- **Pruebas:** `v3/tests/test_verificar_v3.py` (9), con fases falsas ejecutadas de verdad.
- **Mutaciones:** R6–R11 en `v3/mutaciones/v31_mantenimiento.json` (fase F14 del verificador).

## 3. Rutas personales en el empaquetador

- **Se rechaza el paquete** si un archivo de código, pruebas, `sistema/`, `fuentes/` (o un nombre de archivo)
  contiene una carpeta personal: `C:\Users\<nombre>`, `/home/<nombre>` o `/Users/<nombre>`, salvo nombres genéricos
  como `user`. También se rechaza si contiene la carpeta de trabajo de esta máquina en cualquier forma: nativa, POSIX,
  con «\» escapadas o sin la unidad (como aparecen en trazas recortadas).
- **En registros y documentación** (`evidencias/`, `docs/`, `PROGRESO.md`) se sustituyen DENTRO del ZIP por
  `<TRABAJO>` y `<CASA>`. El archivo del disco no cambia y el manifiesto lleva el SHA-256 de lo empaquetado. Así
  desaparece el paso manual de «copia sin rutas».
- **Límite documentado:** una carpeta de trabajo que no es un perfil de usuario solo se reconoce si es la actual; el
  paquete se genera siempre desde el árbol original.
- **Pruebas:** 5 nuevas en `v3/tests/test_empaquetar.py`. **Mutaciones:** R1–R5 y R12. Las 7 mutaciones de la Etapa 8
  siguen detectadas.
- **Fuga encontrada al comprobar la entrega, y corregida:** una búsqueda independiente dentro del ZIP generado
  encontró `<TRABAJO>\\…` en `evidencias/v31_f05/f11_run2_subpruebas.json`: una traza JSON
  recortada SIN unidad NI barra inicial, una forma que la primera versión no cubría. Se añadieron esas formas (solo si
  conservan algún separador), una prueba con la forma exacta y la mutación **R12**. Esa versión del ZIP se descartó
  y la validación integral se repitió completa sobre el código corregido (§1.1).
- **Hallazgo durante el desarrollo:** el propio rechazo detectó una ruta falsa en la especificación de mutaciones
  (PowerShell había escrito `<` como `\u003c`, y `C:\Users\<nombre>` parecía un usuario real). Se reescribió el
  archivo.

## 4. Git local

Ver `docs/V31_GIT_LOCAL.md`. Resumen:
- repositorio en la carpeta del proyecto, ramas `main` (estado verificado) y `mantenimiento-v31`;
- sin remotos, con una guardia `pre-push` comprobada (un `push` de prueba se rechaza y no llega nada);
- `* -text` y `autocrlf = false`: un clon reproduce los 736 archivos con el mismo SHA-256;
- identidad local genérica, sin datos personales; `originales/` fuera del repositorio.
- **Aviso:** se pidió instalar Git solo para el usuario (`--scope user`), pero el instalador pidió permisos de
  administrador y quedó instalado para todo el equipo (`C:\Program Files\Git`).

## 5. `majflt` en Windows

Ver `docs/V31_MAJFLT_WINDOWS.md`. El contador documentado (`PageFaultCount`) no distingue disco de memoria. El de
fallos duros por proceso (`HardFaultCount`) sí: 132 o 260 en lectura fría frente a 0 en caliente, también medido
desde otro proceso. Pero es un campo no documentado oficialmente. **Propuesta:** usarlo con sonda de autocomprobación
y fallo cerrado. Es la decisión **D3** antes de F1.

## 6. Defecto abierto

**V-CON-11** es inestable en Windows (ver §1.1). Mientras no se resuelva, `--completo` en Windows puede fallar en F11 de vez en cuando por esa comprobación. Cuando ocurra, el procedimiento es: comprobar que la única diferencia es V-CON-11 con la firma de memoria (`comparar_ejecuciones.py`) y reanudar. Nunca aceptarlo sin mirar.

## 7. Lo que NO se hizo (como se pidió)

Ni detección automática de pruebas inestables, ni aislamiento con Job Objects, ni llevar los adaptadores a V2-F.1, ni
integrar los diagnósticos, ni paralelizar F3–F10, ni el reto `zomboid_v2`.
