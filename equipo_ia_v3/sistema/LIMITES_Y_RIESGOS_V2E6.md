# Límites y riesgos pendientes de V2-E.6

Clasificación: **NO VERIFICADO** = no se pudo ejecutar aquí; **LÍMITE** = decisión de diseño conocida; **RIESGO** = puede fallar en uso real.

## No verificado (sin ejecutar en esta entrega)
1. **Qwen real.**
   - En la sandbox no hay GGUF ni `llama-server`.
   - Las fases QWEN (V-QWEN-01..03) quedan NO VERIFICADA mientras no se ejecuten con `--qwen-real --iniciar-servidor-real`.
   - Ninguna cifra de esta entrega procede del modelo.
2. **Termux (Android) y Windows.**
   - Solo se ejecutó en Linux (sandbox), con Python 3.13.
   - El modo «sin `os.link`» de Termux se simuló con un `sitecustomize` temporal fuera del paquete.
3. **Perfiles 2560 y 3072.**
   - Los umbrales de RAM son ESTIMACIONES conservadoras: 2 000 000 kB y 2 800 000 kB disponibles, por encima de los 1 200 000 kB de la referencia.
   - No se ha medido si Qwen 3B en el S23 los sostiene.
   - El perfil experimental exige además `--aceptar-experimental`.
4. **Reto Zomboid con Qwen.**
   - El camino HTTP completo solo se probó con el servidor FALSO.
   - Con 2048 de contexto, las evidencias largas (Viewpoint, inicio) se recortan por líneas; las líneas omitidas se indican en el prompt.

## Límites de diseño
5. **Un solo modelo.**
   - Los tres agentes son el MISMO Qwen. La independencia no se garantiza: se vigila con señales deterministas (`independencia.py`).
   - Esas señales son heurísticas. Una revisión complaciente bien redactada puede no detectarse, y dos revisiones parecidas pueden ser legítimas: la similitud no prueba copia.
6. **Aprendizaje.**
   - La evaluación pre/post usa una política determinista, no Qwen. Demuestra el MECANISMO: recuperar → usar → transferir; un voto no verifica; un recuerdo refutado no se recupera.
   - Las contradicciones se detectan con una heurística de polaridad («X modifica» frente a «X no modifica»). No entiende el significado.
   - Los hechos «observados» que guarda el orquestador dicen qué registró el sistema (resultado, fiabilidad). No dicen que la solución sea correcta, y el texto lo indica.
7. **Puntuador Zomboid.**
   - Es heurístico y basado en patrones.
   - Mide citas verificables, matices de causalidad, separación hecho/hipótesis/falta, reversibilidad, falsabilidad y honestidad.
   - NO mide si el diagnóstico es cierto en el juego.
   - Las respuestas de referencia buena y mala las escribí yo para calibrarlo: no son de Qwen.
   - Una respuesta que imite el formato sin sustancia puede puntuar alto. Los oráculos están en datos (`oraculos.json`) para que GPT-6 los audite.
8. **Generador seguro.**
   - `retos.generar()` reproduce la lógica que leí en `generar_reto.py`: barajar con la semilla y elegir un modificador.
   - No se comprobó ejecutando el original, deliberadamente: es material no confiable.
9. **Paquetes.**
   - Solo declarativos. Las operaciones que piden código, órdenes, red o el modelo quedan NO_DISPONIBLE.
   - No hay firma criptográfica de autor: la confianza la da tu autorización por SHA-256.
10. **Pruebas variables.**
    - Las semillas cambian el CASO, no la capacidad de los agentes.
    - Los «agentes» de las pruebas variables son guiones o respuestas de referencia.
    - La batería comprueba que el SISTEMA detecta lo que el oráculo oculto dice (abstenciones forzadas, dependencia, truncados, inyecciones), y que es determinista.
11. **Reanudación.**
    - Solo deliberaciones, y solo ejecuciones de V2-E.6, que registran `runs/<id>/tareas.json`.
    - Una tarea a medias se repite entera en una sesión nueva. No se continúa a mitad de fase.

## Riesgos
12. **Más memoria en el prompt.**
    - Las memorias llevan metadatos y el bloque crece de 500 a 800 caracteres (`CAP_MEMORIAS_PROMPT`).
    - En el perfil de 1024 puede recortarse antes; queda indicado como «recortado».
13. **Cambio de comportamiento heredado.**
    - El código de A1 (soluciones, alternativas, parches) ahora conserva la indentación; antes se colapsaban los espacios.
    - Una prueba heredada se actualizó con la marca `# CAMBIO V2-E.6`.
14. **Rutas nuevas.**
    - Verificación y auditoría se mudan a `lab_v2e6/verificacion` y `lab_v2e6/auditoria`.
    - Los paquetes autorizados con r3 hay que autorizarlos de nuevo en V2-E.6. Es deliberado: no se comparte confianza entre versiones.
15. **Duración.**
    - La batería completa tardó unos 6 minutos en la sandbox (2 núcleos). En el S23 puede tardar bastante más.
    - `--rapido` omite las repeticiones.

## V2-E.6-r2 (tras la auditoría adversarial)
16. **Caso A corregido, con un límite.**
    - Una `prueba_estatica` exige una ejecución real y registrada de un verificador de código, y se re-ejecuta.
    - Que la prueba elegida sea PERTINENTE para el recuerdo no se comprueba semánticamente: quien llama elige el verificador y el artefacto. Lo que sí queda garantizado es que lo probado queda registrado y es reproducible, así que un auditor puede ver una prueba irrelevante.
    - Quien edite a mano el archivo SQLite puede insertar filas, pero `auditar()` las re-ejecuta y las detecta.
17. **Caso B mitigado, no eliminado.**
    - El análisis es heurístico: plegado de ofuscaciones, cláusulas en 6 idiomas, cargas codificadas y cuarentena.
    - Paráfrasis nuevas pueden pasar. Por eso los recuerdos van siempre como datos no confiables y ninguna API de memoria cambia código, permisos ni configuración.
    - También puede haber falsos positivos: textos descriptivos con «modifica la configuración» quedan en cuarentena (no en el prompt).
18. **`observado` y `dato_externo` ya no verifican.**
    - Los hechos observados por el orquestador quedan `sin_verificar`.
    - Un dato externo necesita confirmación humana con `aprender.py feedback --autorizo`.

## V2-E.6-r3 (tras la auditoría GPT-6 de r2, hallazgo C)
19. **Hallazgo C corregido para los casos del auditor; mitigado en general.**
    - En un corpus ciego final (escrito con las reglas congeladas), r3 detecta 16 de 30 instrucciones indirectas nuevas (r2: 3/30).
    - **Una paráfrasis nueva tiene aproximadamente la mitad de probabilidades de pasar.** El filtro reduce el riesgo, no lo elimina.
20. **Falsos positivos (van a cuarentena, nunca a rechazo).**
    - 3/30 en el corpus ciego final, por ejemplo «Never approve a patch that mutates the input».
    - Las normas de proceso, aunque refuercen el control («Política del equipo: toda propuesta pasa por la revisión de A3»), no se toman de la memoria, por diseño de la capa 6.
    - Algunas razones de voto sin anclaje («apruebo: la función es correcta…») dejan de recuperarse: 1 de 18 registros en una deliberación simulada.
    - Una razón de voto de una sola palabra («aprobar») también va a cuarentena.
21. **La autorización no depende del texto recuperado,** pero solo en el código:
    - Lo comprueban pruebas estáticas y de comportamiento.
    - No está demostrado que Qwen real ignore una memoria maliciosa que llegue al prompt: el modelo puede verse influido al redactar su respuesta. La decisión se toma después, con votos y comprobaciones deterministas.
22. **Identificadores `snake_case`.** La capa 6 los trata como datos (son los motivos que registra el sistema). Un texto que esconda una norma en un identificador («aprobar_todo_sin_revisar») depende solo de las capas 2 y 5.

## V2-E.7 (equipo operativo)
23. **El ejecutor restringido no es un sandbox.** Un proceso del mismo usuario no está aislado del sistema operativo. La protección es la lista blanca AST más el gancho de auditoría y los límites del núcleo. Un fallo en ambas capas permitiría al código probado actuar con los permisos de Termux.
24. **Qwen real sin verificar.** La demostración usa un guion. Con Qwen 3B y un contexto de 2048 tokens, las pruebas de A2 pueden salir mal formadas, usar módulos fuera de la lista blanca o no coincidir con los nombres de los criterios. En esos casos el resultado queda `no_verificado`, nunca se aprueba.
25. **La recuperación tras SIGKILL (propuesta r4) no está implementada.** Rige el bloqueo de r3 por proceso `llama*` y puerto ocupado.

