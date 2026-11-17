# Contrato de personalidad v1 (`eq2/personalidad`, versión 1.0)

Es el formato con el que un módulo **externo** (por ejemplo, el módulo de personalidades que mencionáis) podrá entregar un perfil a Equipo IA.

**En V2-E.5-r3 solo se valida; no se guarda ni se activa nada.**
- Comando: `python3 -B perfiles.py validar-contrato --archivo F.json`.
- Función: `eq2.personalidad.validar_contrato(doc)`.

## Documento
```json
{
 "contrato": "eq2/personalidad",
 "version_contrato": "1.0",
 "agente": "A1",
 "perfil": {
  "rasgos": ["curioso", "paciente"],
  "estilo": {"tono": "neutral", "verbosidad": 3, "formato": "mixto"},
  "preferencias": {"ejemplos": true, "explicar_razonamiento": true, "pedir_aclaraciones": "a_veces"}
 },
 "origen": {"tipo": "modulo_externo", "proveedor": "nombre del módulo", "version_modulo": "0.1"},
 "creado": "2026-10-26T10:00:00-03:00",
 "notas": "opcional, ≤ 300 caracteres"
}
```
La descripción campo a campo está en `personalidad_v1.json`. Las reglas del `perfil` son exactamente las de la elección propia de cada agente (`PERSONALIDAD.md` §2).

## Reglas
- **Esquema cerrado.** Una clave desconocida da `fuera_del_esquema`. Si la clave alude a permisos, rol, función, seguridad, modo B, criterios, límites, evaluación, votos, instrucciones o sistema, da `maliciosa`. Ocurre lo mismo en `origen`.
- **Versiones.** Se admiten las versiones menores `1.x`; `2.0` o una versión sin el formato `1.x` da `invalida`.
- **Validación del perfil.** Se rechazan los rasgos prohibidos o contradictorios y los valores fuera de rango. Las notas con marcas de inyección dan `maliciosa`.
- **Lo que nunca hará.** La personalidad **nunca** podrá modificar permisos, políticas de seguridad, límites, criterios de evaluación, votos ni decisiones críticas.
- **Integración futura.** Cuando se autorice, un documento válido solo podrá entrar como **propuesta**, pendiente de la aprobación del usuario, con el origen `modulo_externo` registrado. No se hará en esta versión.

## Ejemplos (`ejemplos/`, con la categoría esperada en `esperado.json`)
| Archivo | Resultado esperado |
|---|---|
| `valido_a1.json` | válido |
| `valido_version_menor.json` | válido |
| `invalido_permisos.json` | maliciosa |
| `invalido_rasgo_rol.json` | maliciosa |
| `invalido_contradictorio.json` | contradictoria |
| `invalido_version_mayor.json` | inválida |
| `invalido_clave_extra.json` | fuera del esquema (`avatar`) |

Las pruebas `test_v2e5r3.TestContratoPersonalidad` comprueban todos los ejemplos.
