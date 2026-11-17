# Equipo IA V3.1 F1 — X1: pruebas inestables (V-CON-11) sin aceptar regresiones (2026-11-11)

**Autorizado** en la orden oficial de F1 (§3). `sistema/` (V2-F.1) sin modificar; la línea base de Linux sin
modificar; en la de Windows NO cambia ninguna de sus 503 pruebas (solo se añade una declaración).

## 1. Caracterización (evidencias/v31_f1/x1/)

La subprueba `test_v2e5.TestAdaptadores.test_termux_y_linux_dan_lo_mismo_que_el_codigo_anterior` (línea 375)
compara DOS lecturas sucesivas de la memoria disponible. En Windows el lanzador sirve la memoria REAL
(`GlobalMemoryStatusEx`), que cambia entre lecturas.

| Medición (`x1_caracterizar.py`) | PC en reposo | Con carga de memoria (`x1_carga_memoria.py`, 1 GiB en bucle) |
|---|---|---|
| A. Pares de lecturas de la API distintos | 1,7 % (máx. 4272 kB) | 81,9 % (máx. 25 920 kB) |
| B. Pares por el camino de la prueba (Linux/Termux) | 1,6 % / 1,7 % (máx. 2116 kB) | 89,5 % / 81,9 % (máx. 9316 kB) |
| C. Prueba completa, 40 ejecuciones | **3 fallos** (24–640 kB) | **37 fallos** (216–5256 kB) |

Conclusión: no es una regresión, es una suposición de la prueba («dos muestras de una magnitud cambiante son
iguales») que en Linux casi siempre se cumple y en Windows no. Con carga, deja de ser «a veces» y pasa a ser «casi
siempre»: por eso la tolerancia NO puede basarse solo en repetir.

## 2. Clasificación explícita: veredicto INESTABLE (`v3/linea_base.py`)

La línea base declara la inestabilidad (`inestables`, desde `v3/causas_windows.json`; causa
`WIN_MEMORIA_REAL_CAMBIANTE`). Una REGRESION o un CAMBIO del verificador pasa a **INESTABLE** solo si se cumplen
TODAS estas condiciones; si falla una, la diferencia conserva su veredicto y la puerta falla:

1. La comprobación falla (FALLO) con el MISMO número de pruebas que la línea base; la traza solo tiene FAIL, ningún
   ERROR, y su recuento coincide con la firma.
2. Están TODOS los fallos conocidos de la línea base, y cada fallo de más es EXACTAMENTE el declarado:
   - misma subprueba;
   - un único marco en `test_v2e5.py`, línea 375, con el mismo código;
   - mensaje `A != B` con A, B > 0 y |A − B| ≤ 32 768 kB, sin texto de más.
3. Repetida aislada 5 veces (orden y opciones del verificador, por el lanzador), la subprueba **pasa al menos 3**
   (mayoría estricta). Cada repetición fallida vuelve a ser exactamente el fallo declarado; un fallo distinto la
   descarta al momento.

**Visibilidad:**
- `v3/linea_base.py` sale con **4** («igual salvo N pruebas INESTABLES confirmadas, NO CONCLUYENTES en esta
  ejecución»), nunca con 0.
- Cada intento, confirmado o no, queda en `resultado.json` (`inestabilidad`), y las repeticiones en
  `inestables/<id>/`.
- `verificar_v3.py` admite el 4 SOLO en F11. La fase queda marcada `con_inestables`, y el estado general lo dice:
  «CORRECTO CON PRUEBAS INESTABLES CONFIRMADAS (F11)».
- `--reanudar` nunca reutiliza esa fase.

**Tolerancia de 32 MiB:** por encima del máximo medido con carga (25 920 kB en la API) y muy por debajo de los
errores plausibles: unidades (×1024) u otro campo de memoria, de gigabytes. Una regresión pequeña y constante
(4 kB) cae dentro de la tolerancia, pero falla en TODAS las repeticiones y no se confirma (probado con una copia
mutada de `sistema/`).

## 3. Pruebas y mutaciones

- `v3/tests/test_inestables.py` (14 pruebas):
  - la traza REAL del intento 1 se explica;
  - 14 desviaciones de la firma no se explican, con un control positivo;
  - mayoría estricta y fallo distinto en las repeticiones;
  - código 4 visible;
  - validación de declaraciones;
  - **dos regresiones REALES sembradas en una copia de `sistema/`**: un desplazamiento de 4 kB (0 de 5 correctas, no
    se confirma) y un error de unidades (fallo distinto, no se confirma).
- `v3/tests/test_verificar_v3.py`: el 4 solo vale en F11, queda marcado y no se reutiliza.
- **Fase F15** del verificador integral (`v3/mutaciones/v31_f1_inestables.json`): 16 mutaciones, cada una quitando
  una de las salvaguardas. **16/16 detectadas.** R13 (en F14): el 4 admitido en otra fase.

## 4. Comprobación con ejecuciones reales (`x1_reproducir_ejecuciones.py`)

| Ejecución de F11 | Sin X1 | Con X1 |
|---|---|---|
| `lb082749` (intento 1 del mantenimiento, el que falló) | 1 (CAMBIO en V-CON-11) | **4**: INESTABLE, diferencias 1024 y 8 kB, confirmada 5/5 |
| `lb091325` (reanudación) | 0 | 0 |
| `lb094925` (validación final) | 0 | 0 |

## 5. Límites (sin maquillar)

- Una regresión que fallara de forma INTERMITENTE con exactamente la misma firma, dentro de la tolerancia y en menos
  de la mitad de las repeticiones, no se distinguiría de la inestabilidad. Es el límite de cualquier criterio
  estadístico y está acotado a una sola subprueba y una sola línea.
- Los fallos CONOCIDOS de V-CON-11 se identifican por subprueba (como ya hacía la puerta, que solo comparaba el
  recuento), no por su texto.
- Con el PC muy cargado, la confirmación falla (mayoría no alcanzada) y F11 FALLA: es fallo cerrado, no un
  aprobado. Hay que repetir con el PC menos cargado.
- Solo se admiten declaraciones sobre comprobaciones del verificador de V2-F.1 (las únicas con traza por
  subprueba).
