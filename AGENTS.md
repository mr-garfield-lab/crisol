# Equipo IA — Instrucciones para agentes de desarrollo

## Objetivo
Desarrollar y auditar Equipo IA: sistema multiagente local A1/A2/A3 con Qwen, memoria persistente, debate, herramientas controladas y ejecución supervisada en Android/Termux.

## Reglas obligatorias
1. No utilizar APIs externas de pago ni solicitar credenciales.
2. No realizar operaciones destructivas, borrar archivos, eliminar historial ni cerrar procesos ajenos.
3. No modificar directamente la rama main. Trabajar en ramas independientes y proponer pull requests.
4. No sobrescribir versiones originales. Mantener copias recuperables y cambios trazables.
5. No activar herramientas peligrosas ni ampliar permisos sin autorización explícita del usuario.
6. No afirmar que una prueba simulada demuestra funcionamiento real en Android.
7. No fusionar cambios automáticamente con main.
8. Respetar los límites de recursos, costos y permisos configurados.

## Antes de programar
- Inspeccionar la estructura real del repositorio y detectar la versión base.
- Identificar dependencias, módulos existentes y pruebas disponibles.
- Si Contexto Ligero / Graphyfi está instalado, consultar su documentación y utilizar su grafo para localizar archivos relevantes.
- No inventar comandos del grafo: comprobar primero su interfaz real.
- Si faltan archivos, herramientas o dependencias, documentarlo y no fingir que existen.

## Desarrollo
- Dividir las misiones grandes en tareas independientes y verificables.
- Priorizar funciones reales y demostrables sobre simulaciones adicionales.
- Mantener compatibilidad con Python y Termux cuando corresponda.
- Conservar los mecanismos de seguridad, permisos, STOP y memoria.
- Cada cambio debe incluir pruebas adecuadas y documentación.

## Colaboración
- Codex: implementación y corrección de código.
- Claude: revisión de arquitectura, seguridad e integración.
- Copilot: tareas auxiliares y revisiones.
- Estos roles son objetivos de coordinación, no automatizaciones ya activadas.
- Intercambiar resultados mediante ramas, commits, pull requests e informes.
- No modificar simultáneamente los mismos archivos sin coordinación.

## Guardado y recuperación
- Realizar commits al completar unidades coherentes de trabajo.
- Mantener PROGRESO.md con tareas terminadas, pendientes, bloqueos y siguientes pasos.
- Registrar los comandos de prueba y sus resultados.
- Ante límites de tiempo, contexto o cuota, priorizar guardar el estado y documentar cómo continuar.
- No prometer reanudación automática sin un mecanismo comprobado.

## Pruebas y entregables
- Distinguir REAL, SIMULADO, OMITIDO y FALLIDO.
- Registrar errores sin ocultarlos.
- Preparar un comando integral de pruebas cuando sea viable.
- Generar un ZIP autocontenido por versión mediante el flujo de empaquetado configurado, sin incluir secretos, modelos GGUF ni datos privados.
- Incorporar manifiesto de archivos, SHA-256, resumen de cambios y resultados de pruebas.
- Las pruebas de Qwen real en Samsung S23 requieren validación específica en Termux.

## Prioridades iniciales
1. Auditar las versiones existentes de Claude y Codex.
2. Integrar módulos compatibles sin perder funcionalidades.
3. Verificar que A1, A2 y A3 ejecuten tareas reales.
4. Mejorar memoria, herramientas y recuperación de tareas.
5. Incorporar Contexto Ligero como ayuda para localizar dependencias.
6. Automatizar pruebas, evidencias y paquetes ZIP.
7. Mantener la rama estable protegida de cambios no auditados.

## Condición de finalización
Una tarea solo está terminada cuando existen cambios guardados, pruebas documentadas, evidencia verificable y una explicación clara de las limitaciones pendientes.

## Para el asistente de IA de quien usa Crisol (Claude, Gemini, GPT, Codex…)

Si una persona te pide ayuda con Crisol en su propio PC:

1. **Empieza por leer, no por cambiar.** Ejecuta `py -B -X utf8 equipo_ia_v3/perfiles/equipo_perfil.py detectar --json`
   y `... recomendar --json`, y `py -B -X utf8 comprobar_todo.py --json`. Todo eso solo lee.
2. **Propón; la persona decide.** No cambies modelos, topes ni configuración sin su sí expreso.
3. **Nunca subas los topes de VRAM o de temperatura ni quites el STOP.** Si el perfil dice que algo no cabe, recomienda un
   modelo o una cuantización menor.
4. **Los modelos los elige la persona.** No descargues ninguno sin su permiso; dile el nombre, el origen y el tamaño.
5. **El código que escribe un cerebro solo se ejecuta dentro del laboratorio de Blender, con sus filtros.** No es una caja
   aislada del sistema operativo (corre con los permisos del usuario): nunca lo ejecutes en otro sitio ni quites filtros.
6. **Privacidad:** el informe de `equipo_perfil.py informe` no lleva datos personales; no pidas registros con rutas o
   nombres sin avisar de lo que contienen.
7. **Distingue lo medido de lo estimado** en lo que respondas (los perfiles lo indican).
