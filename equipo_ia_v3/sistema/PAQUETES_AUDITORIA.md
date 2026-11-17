# Paquetes de auditoría adicionales (formato `eq2/auditoria`, versión 1)

Sirven para que GPT-6, u otro auditor, añada comprobaciones **después** de la entrega, sin reinstalar Equipo IA y **sin ejecutar código del paquete**.

## Flujo
1. **El auditor prepara el paquete.** Escribe una carpeta con `manifiesto.json` y archivos de datos, y ejecuta:
   ```
   python3 -B herramientas/construir_paquete.py CARPETA auditoria_adicional.zip
   ```
   La herramienta calcula los SHA-256, genera un ZIP determinista y lo valida.
2. **El usuario coloca el ZIP** en `$TMPDIR/equipo_f2/auditoria/entrada/`.
3. **El verificador lo detecta, pero no lo ejecuta.** `python3 -B verificar.py --solo V-CON-02` lo valida, lo registra en `auditoria/registro.jsonl` y lo marca como «NO AUTORIZADO».
4. **El usuario lo revisa y lo autoriza:**
   ```
   python3 -B verificar.py --autorizar-paquete $TMPDIR/equipo_f2/auditoria/entrada/auditoria_adicional.zip
   ```
   Se muestran el autor, el origen, el SHA-256 y cada prueba con su operación. La autorización se guarda en `auditoria/autorizados.json`, ligada a **ese SHA-256 exacto**: si el ZIP cambia, deja de estar autorizado.
5. **Ejecución.** La siguiente ejecución de `verificar.py` incorpora sus pruebas al catálogo (`V-CON-02`). Cada una aparece como `[ID-PAQUETE:ID-PRUEBA] OK / FALLO / NO_DISPONIBLE`.

**Un hash correcto solo prueba la INTEGRIDAD** (que el contenido es el declarado), **no que el paquete sea confiable.** La confianza la decide el usuario al autorizarlo.

## Manifiesto (esquema cerrado)
```json
{
 "formato": "eq2/auditoria", "version_formato": 1,
 "id": "AUD-GPT6-0001", "titulo": "…", "autor": "GPT-6", "origen": "auditoría de V2-E.5-r3",
 "creado": "2026-10-26T12:00:00-03:00", "compatible_con": ["f2-v2e5-r3"], "descripcion": "…",
 "archivos": {"datos/casos.json": "<sha256>"},
 "pruebas": [
  {"id": "G-01", "objetivo": "…", "operacion": "clasificar_criticas",
   "parametros": {"archivo": "datos/casos.json"},
   "criterio": {"veredictos": {"X1": ["falsa_no_detectada"]}, "resumen": {"casos": 3}},
   "recursos": {}, "segundos_max": 60}
 ]
}
```
- **Compatibilidad.** Si la versión actual no figura en `compatible_con`, el paquete aparece como «INCOMPATIBLE» y no se ejecuta.
- **Recursos.** Son `{nombre: bool}`. `red`, `modelo`, `python` y `comando` a `true` hacen que la prueba quede como NO_DISPONIBLE.
- **Límite de tiempo.** `segundos_max` va de 1 a 600.

## Operaciones admitidas (lista cerrada, implementadas por Equipo IA)
| Operación | Datos | Criterio |
|---|---|---|
| `clasificar_criticas` | casos etiquetados en el formato del corpus (`evaluacion_criticas.validar_casos`) | `veredictos` por caso y/o campos de `resumen` |
| `validar_perfil` | `[{respuesta, categoria_esperada}]` | cada categoría coincide |
| `motivo_parada` | `[{motivo, es_parada}]` | `inferencia.parada_de` coincide |
| `analisis_estatico` | `{"archivos": {ruta: texto}}` (solo AST; no ejecuta nada) | `tipos_error` exactos |
| `huella_archivo` | `parametros: {ruta, sha256}` de un archivo de la versión instalada (la ruta no puede salir de ella) | SHA-256 igual |
| `repetir_prueba` | `parametros: {prueba: "test_modulo[.Clase[.metodo]]", repeticiones: 1–20}`: una prueba **existente** de Equipo IA, no del paquete | todas las repeticiones OK |

Cualquier otra operación (`python`, `comando` o una desconocida) se marca **NO_DISPONIBLE** y no se ejecuta.

## Reglas de seguridad del contenedor
- **Lectura.** El ZIP se lee **en memoria**: no se extrae nada al disco.
- **Nombres.** Se rechazan:
  - rutas absolutas o con `..`;
  - `\`, `C:`, caracteres de control;
  - duplicados.
- **Contenido.** Se rechazan:
  - enlaces simbólicos;
  - entradas cifradas;
  - extensiones distintas de `.json`, `.md` y `.txt`;
  - archivos no declarados;
  - SHA-256 que no coinciden.
- **Límites:**

  | Límite | Valor |
  |---|---|
  | ZIP | 2 MB |
  | Archivos | 50 |
  | Tamaño por archivo | 1 MB |
  | Descomprimido en total | 5 MB |
  | Tasa de compresión | 50 |
  | Pruebas | 100 |
- **Registro.** Cada paquete detectado, rechazado, autorizado o ejecutado queda en `registro.jsonl`, con su SHA-256, su estado y la versión.
- **Aislamiento.** Nada del paquete sobrescribe el núcleo ni el proyecto original.

## Capacidades pendientes (documentadas, no improvisadas)
- **Pruebas con código Python** del auditor: necesitan un aislamiento **real** (proceso sin red, sin acceso al laboratorio, con límites de CPU y memoria) que hoy no existe en Termux. Siguen como NO_DISPONIBLE.
- **Firma criptográfica de paquetes** (para reconocer al autor sin depender de la autorización manual): no existe.

## Ejemplo incluido
`auditoria_ejemplo/auditoria_ejemplo.zip`, construido desde `auditoria_ejemplo/fuente/`. Usa cada operación y contiene una prueba `python` que debe aparecer como NO_DISPONIBLE. Viaja con la versión: su SHA-256 está en el manifiesto de la entrega, y se ejecuta en `V-CON-01`.

## V2-E.6: paquetes de DESAFÍO (`eq2/desafio` v1)
- **Contenedor:** el mismo que los de auditoría, con las mismas reglas: lectura en memoria, extensiones `.json`/`.md`/`.txt`, SHA-256 por archivo, límites de tamaño y de tasa de compresión, y rechazo de traversal, enlaces, cifrado y duplicados.
- **Formato:** `"formato": "eq2/desafio"`, `"version_formato": 1`. Los dos formatos admitidos están en `FORMATOS`.
- **Material del reto:** `parametros.reto` nombra una carpeta declarada que debe contener `casos.json` y `oraculos.json`. Las evidencias son los `.txt` que nombran los casos.
- **Operación `generar_reto`:** recibe `{reto, semilla, n}` y lo compara con `criterio.casos` (el orden esperado). Usa el generador PROPIO y seguro.
- **Operación `puntuar_reto`:** recibe `{reto, archivo}`. El archivo es una lista de `{id, caso, texto, total_min, total_max, penalizaciones_esperadas}`; se puntúa cada respuesta con el material del paquete.
- **Recursos:** una prueba que pide el `modelo`, `python`, un `comando` o la `red` queda **NO_DISPONIBLE**.
- **Ejemplo incluido:** `retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip` (fuente en `fuente/`). El verificador lo comprueba en V-CON-03.
- **Rutas en V2-E.6:**
  - Los paquetes externos van en `$TMPDIR/equipo_f2/lab_v2e7r3/auditoria/entrada/`.
  - Las autorizaciones, en `lab_v2e7r3/auditoria/autorizados.json`.
  - Las autorizaciones de r3 no se heredan.
