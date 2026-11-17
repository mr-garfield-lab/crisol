# Equipo IA V3

Sistema multiagente local (A1 programador, A2 analista, A3 revisor crítico) construido SOBRE Equipo IA V2-F.1,
**sin modificarlo**.

- **Base:** V2-F.1 está en `sistema/`.
- **Añadidos de V3:** traza unificada y verificable, grafo y contexto de código, programación controlada
  (propuesta → autorización del usuario → aplicación), verificador de citas, memoria individual, episódica y de
  proyecto, y planificación de recursos para el PC.

> **Estado: NO listo para producción.**
> - Todo se verificó en Linux con agentes SIMULADOS.
> - Nada se ha validado con Qwen real, en Android ni en Windows.
> - La ejecución de código generado sigue DESHABILITADA (SEG-01).

## Inicio rápido (desde esta carpeta)

```sh
python3 -B verificar_v3.py                 # F0–F9: integridad, pruebas y mutaciones (unos 4 min)
python3 -B verificar_v3.py --completo      # además la línea base de 503 pruebas de V2-F.1 (unos 12 min)
python3 -B equipo3.py --help
```

Ejemplo:

```sh
cd sistema && python3 -B equipo.py demo funcion && cd ..   # A1/A2/A3 SIMULADOS (V2-F.1)
python3 -B equipo3.py traza importar LAB-001               # Etapa 1
python3 -B equipo3.py traza deliberacion LAB-001/E001      # Etapa 4
python3 -B equipo3.py cambios proponer-desde-traza LAB-001/E001 --proyecto demo --archivo mediana.py
python3 -B equipo3.py cambios listar                       # y luego: cambios autorizar PROP-0001 --sha <12 caracteres>
python3 -B equipo3.py memoria consultar A2 "revisar la mediana de una lista"
python3 -B equipo3.py pc recomendar                        # Etapa 6: ESTIMACIONES
```

## Documentación

| Documento | Contenido |
|---|---|
| `PROGRESO.md` | Estado por etapa, restricciones vigentes y cómo continuar |
| `docs/ETAPA0_AUDITORIA.md` … `docs/ETAPA7_AUDITORIA.md` | Informe de cada etapa, con sus pruebas, mutaciones, hallazgos y limitaciones |
| `docs/INVENTARIO_FUNCIONES.md` | Qué se verificó y cómo: REAL, SIMULADO, ESTIMACIÓN o NO VERIFICADO |
| `docs/GUIA_WINDOWS.md`, `docs/GUIA_TERMUX.md` | Uso en cada plataforma, ambos NO validados |
| `evidencias/` | Registros de cada verificación, cada uno con su `LEEME.md` |

## Componentes reutilizados (copias IDÉNTICAS, con `ORIGEN_SHA256.json`)

- `contexto_ligero/`: Contexto Ligero V3.5 (índice, dependencias y paquetes de contexto).
- `complementos_codex/`: complementos de Codex (memoria y puente con V2-F.1).

El paquete incluye también `../fuentes/codex_complementos` y `../fuentes/contexto_ligero_v35`, las selecciones
originales, que la línea base necesita para ejecutar sus pruebas.
