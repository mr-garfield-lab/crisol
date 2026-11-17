# Extensiones futuras: solo interfaces (V2-E.5)

Este documento describe **interfaces**, no funciones disponibles. **Nada de lo que aparece aquí se implementa en V2-E.5**, salvo lo que ya existía en `src/eq2/extensiones.py` desde V2-E.2:
- el complemento Python (solo análisis estático);
- los complementos de otros lenguajes, declarados pero sin implementar;
- la lista de comprobación de migraciones;
- `ConfiguracionModular`.

## Reglas comunes a todas las extensiones
1. **Opcionales y desactivadas por defecto.**
   - Una extensión desactivada no se importa, no crea hilos ni procesos y no reserva memoria.
   - `test_v2e5.TestExtensionesFuturas.test_ningun_modulo_visual_se_carga` comprueba que importar todo `eq2` no carga ninguna biblioteca gráfica (tkinter, pygame, PIL, Qt, kivy, wx, cv2).
2. **No amplían permisos.**
   - Ninguna extensión puede activar el Modo B, la ejecución de código generado, la red, privilegios ni la instalación de dependencias.
   - `ConfiguracionModular.desde_dict` lanza `PermissionError` con esas claves y `ValueError` con cualquier clave desconocida: `avatar`, `personalidad` y `gui` se rechazan hoy.
3. **Solo stdlib en el núcleo.** Una extensión que necesite una dependencia externa irá en un paquete aparte, con aprobación explícita del usuario.
4. **Trazabilidad.** Toda acción de una extensión que afecte a datos del laboratorio se registra en la auditoría existente. Ninguna escribe fuera de `$TMPDIR/equipo_f2` ni en `~/equipo-ia`.
5. **Código de terceros = no confiable.** Igual que los tipos especializados de V2-E.4-r2, una extensión externa solo se **declara**. Ejecutarla exigirá aislamiento real y una autorización del usuario que hoy no existen.

## 1. Plugins de lenguajes
Interfaz (existente): `PluginLenguaje` con
- `nombre`, `extensiones` y `estado` (`no_implementado` | `estatico`);
- `analizar_estatico(archivos) -> dict`;
- `ejecutar_pruebas()`, que siempre lanza `EjecucionDeshabilitada`.

Pendiente:
- análisis estático real para Java, C++, C#, JavaScript y Rust;
- prompts por lenguaje.

Un plugin **nunca** compila ni ejecuta código mientras el Modo B esté deshabilitado.

## 2. Migraciones entre lenguajes (conservando los originales)
Interfaz (existente): `EvaluadorMigracion.evaluar(origen, destino, archivos)`, que devuelve una lista de comprobación con `viable = None`.

Contrato previsto:
- La migración produce un **candidato nuevo** (`Candidato`, `RepositorioCandidatos`). Los archivos de origen **no se modifican ni se borran nunca**: el original queda archivado con su SHA-256.
- Se migra por módulos, con una interfaz estable entre ellos.
- La equivalencia solo puede afirmarse con pruebas de caracterización **ejecutadas**. Sin Modo B, el resultado es siempre «no verificado».

## 3. ModLab (análisis y optimización de mods y videojuegos)
**No se implementa.** Interfaz prevista:
- `ModLab.inventariar(carpeta_copia) -> dict`: lista de archivos, formatos y tamaños de una **copia** de solo lectura.
- `ModLab.analizar(inventario) -> informe`: análisis estático (scripts, configuraciones, conflictos de nombres).
- `ModLab.proponer(informe) -> [Candidato]`: propuestas en candidatos nuevos.

Restricciones:
- nunca escribe en la instalación del juego;
- no inyecta, no parchea binarios y no se conecta a servidores;
- no evita protecciones anti-trampas ni DRM.

## 4. AvatarLab (avatares chibi 2D, animaciones y expresiones)
**No se implementa.** Interfaz prevista:
- `Avatar(id, hoja_sprites, expresiones: dict[str, rango])`.
- `AvatarLab.expresion_para(evento) -> str`: traduce eventos ya existentes (voto, error, tarea completa) a una expresión. **Solo lee** eventos; nunca los genera ni los altera.
- Recursos (imágenes) en un paquete opcional aparte.

Coste cero cuando está desactivado:
- sin importación;
- sin hilo de animación;
- sin temporizadores;
- sin lectura de imágenes.

El núcleo no depende de él.

## 5. Personalidades (básicas, con adaptación gradual y memoria controlada)
**Actualización V2-E.5-r2:** las **bases** ya existen en `src/eq2/personalidad.py`; están descritas en `PERSONALIDAD.md`.
- Opcional y desactivado por defecto.
- Cada agente elige su perfil inicial.
- Toda decisión la toma el usuario.

**Sigue sin implementarse:**
- el uso del perfil en los prompts;
- la adaptación automática;
- avatares, voces, diálogos entre agentes y emociones.

**La personalidad nunca modifica los permisos de seguridad.**
- Solo describe estilo y preferencias no críticas.
- Los campos modificables son una lista cerrada que impone la base de datos.
- No puede leer ni escribir `MODO_B_HABILITADO`, los presupuestos, los límites de recursos, el validador, los votos ni la fiabilidad.
- No altera las instrucciones del protocolo de deliberación.

## 6. Interfaz gráfica para PC
**No se implementa.** Contrato previsto:
- La GUI es un **cliente** que lee los archivos JSON de estado (`estado_actual.json`, `summary.json`, `informe.json`) y la auditoría.
- Solo puede invocar las mismas órdenes que la CLI (`ejecutar_v2.py`, `auditar.py`, `supervisar.py`), sin rutas privilegiadas.
- No contiene lógica del núcleo; el núcleo funciona igual sin ella.
- Se distribuye como paquete opcional para Windows 10/11 y Linux, y depende de que esas plataformas estén verificadas (`PLATAFORMAS.md`, fases 2 y 3).
