# Contexto Ligero V3.5

Motor local de búsqueda, dependencias y contexto verificable, desarrollado sobre
una copia de V3.4. V3.4 y Equipo IA se conservan como referencias independientes.

Empiece por [ESTADO_ENTREGA.md](ESTADO_ENTREGA.md) y [GUIA_V35.md](GUIA_V35.md).
El comando único de pruebas crea resultados nuevos sin instalar paquetes ni
recurrir a servicios externos:

```sh
python -B EJECUTAR_PRUEBAS.py
```

Python 3.10+, SQLite y POSIX son suficientes para el modo básico. El comando es
compatible con Termux; consulte el estado de la validación física en el informe.
El conteo básico es estimado; el vocabulario GPT-2 incluido permite conteo real
opcional con una biblioteca previamente disponible. No representa exactamente
los tokens de Claude ni de otros modelos.

`query --explain` muestra alternativas. `packet` es navegación; `bundle` incluye
código completo y soporte verificado. Use `--require` para contratos críticos y
revise avisos y dependencias. Los rangos de código se compactan sin perder líneas
cuando esa representación ahorra; `--line-style numbered` conserva la numeración
anterior. El soporte de símbolos de más de 200 líneas es optativo y acotado.

No se garantiza que el análisis estático conozca dependencias dinámicas ni que un
modelo termine una tarea. Antes de compartir, revise la redacción de secretos.
