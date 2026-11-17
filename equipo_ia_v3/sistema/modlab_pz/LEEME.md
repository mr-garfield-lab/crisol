# Laboratorio experimental de mods Project Zomboid (PZ ModLab 0.1)

**Añadido independiente** a Equipo IA V2-E.7; no modifica el núcleo, ni arranca Qwen, ni ejecuta Lua ni Java. Esta versión NO es un emulador funcional de Project Zomboid: incluye un inspector ZIP y una máquina de estados propia para escenarios declarativos. Sus resultados no certifican compatibilidad del juego ni de los mods.

## Comandos (desde `modlab_pz/`)

```bash
python3 -B laboratorio.py simular escenarios/inventario_demo.json --salida /ruta/nueva/LAB-PZ-001
python3 -B laboratorio.py inspeccionar /ruta/al/mod.zip --salida /ruta/nueva/LAB-PZ-002
python3 -B test_laboratorio.py
```

El destino debe ser un directorio inexistente: nunca sobrescribe resultados. Se crean `resultado.json` y `MANIFIESTO_SHA256.txt`. En error se conserva `error.txt`.

## Alcance y siguientes fases

1. Integración opcional con `equipo.py` mediante tareas LAB-NNN: un adaptador posterior podrá invocar el laboratorio solo con autorización del usuario y con ejecución controlada.
2. Ejecutar scripts Lua reales requiere intérprete y API simulada; **no** cargar mods de terceros en el proceso Termux sin aislamiento de sistema operativo.
3. Validación diferencial con juego/servidor real en PC aislado y medición de falsos positivos.
4. Respetar licencias de mods: no incluir mods ajenos en la distribución; mantener procedencia, permiso y derechos del juego.

Este módulo no usa código del juego ni contiene mods de terceros. Las referencias a `Events` son reconocimiento de patrones, no prueba de sintaxis ni comportamiento.

## Ampliación 0.2
Incluye analizador Lua estático, comprobación sintáctica opcional mediante luac para fixtures confiables, contrato de integración con agentes, escenario de fallo intencional y pruebas propias. No ejecuta scripts Lua de terceros. No modifica equipo.py.
