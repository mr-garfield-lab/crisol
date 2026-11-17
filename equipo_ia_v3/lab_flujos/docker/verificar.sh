#!/bin/sh
# Verificación sin GPU del banco de flujos grandes (dentro de la imagen o en cualquier Linux con Python 3.12).
# Ejecutar desde equipo_ia_v3/. Sale con 0 solo si las comprobaciones del banco pasan.
set -u
echo "== Python: $(python --version 2>&1)"
python - <<'EOF'
import sqlite3
c = sqlite3.connect(":memory:")
try:
    c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    print("== SQLite con FTS5: sí")
except Exception as e:
    print("== SQLite con FTS5: NO", e)
EOF

echo
echo "== 1/3 Pruebas propias de Contexto Ligero V3.5 (informativas: algunas dependen de archivos que no van en el paquete)"
(cd ../fuentes/contexto_ligero_v35 && python -B -m unittest discover -s tests -p "test_*.py" 2>&1 | tail -4)

echo
echo "== 2/3 Comprobaciones del banco de flujos con cerebros falsos"
python -B lab_flujos/humo/comprobar_sin_gpu.py
r=$?
echo
echo "== 3/3 Lectura de Java (mod de ejemplo estilo Forge/Fabric)"
salida_java=$(python -B lab_flujos/humo/comprobar_java.py 2>&1)
rj=$?
echo "$salida_java" | grep -v "^\[PASA\]"
[ "$r" -eq 0 ] && r=$rj
echo
if [ "$r" -eq 0 ]; then echo "RESULTADO: OK (todas las comprobaciones del banco pasan)"; else echo "RESULTADO: FALLO (código $r)"; fi
exit "$r"
