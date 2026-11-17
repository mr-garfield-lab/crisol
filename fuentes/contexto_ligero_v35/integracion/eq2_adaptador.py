"""Puente opt-in para Equipo IA; conserva su constructor, saneado y límites.

No modifica archivos del proyecto, no llama modelos, no activa monkey-patches.
El contexto se añade completo como dato no confiable o se omite completo.
"""
from pathlib import Path

NOMBRE_BLOQUE = "contexto_ligero_v33"


class ProveedorContexto:
    """Consulta un índice previamente creado; no reindexa ni consume APIs."""

    def __init__(self, root, db_path, budget=600, limit=4):
        self.root = Path(root).resolve(strict=True)
        self.db_path = Path(db_path)
        self.budget = budget
        self.limit = limit

    def obtener(self, consulta):
        if not self.db_path.is_file() or self.db_path.is_symlink():
            raise ValueError("Crear antes un índice V3.3 regular mediante scan")
        from contexto_v3 import connect, packet
        db = connect(self.db_path)
        try:
            return packet(self.root, db, consulta, budget=self.budget, limit=self.limit)
        finally:
            db.close()


def agregar_contexto(prompt, paquete, *, requerido=False):
    """Añade METADATOS a un Prompt de eq2; devuelve (prompt, informe).

    El prompt ya construido se conserva entero como parte fija. Los bloques
    existentes no se recortan para abrir espacio. Si el paquete no cabe entero,
    se devuelve un Prompt equivalente y se anota la omisión. La decisión sobre
    abortar una tarea que necesita ese contexto pertenece al llamante.

    No usar para pegar código indentado: el saneado original de eq2 colapsa
    espacios. Los snippets deben auditarse fuera de este puente de metadatos.
    """
    from eq2 import contexto
    if not isinstance(paquete, str):
        raise TypeError("paquete debe ser texto")
    if not paquete.strip():
        raise ValueError("paquete vacío")
    bloque = contexto.Bloque(NOMBRE_BLOQUE, paquete, 99, len(paquete))
    nuevo = contexto.construir(prompt.sistema, prompt.usuario, [bloque], prompt.max_gen)
    incluido = (NOMBRE_BLOQUE not in nuevo.omitidos and
                NOMBRE_BLOQUE not in nuevo.recortados)
    if not incluido:
        if requerido:
            raise contexto.ContextoExcedido("No cabe entero el contexto V3.3 requerido")
        # El constructor de eq2 puede recortar bloques. No aceptar un mapa parcial.
        nuevo = contexto.construir(prompt.sistema, prompt.usuario, [], prompt.max_gen)
        nuevo.omitidos.append(NOMBRE_BLOQUE)
    nuevo.omitidos = list(dict.fromkeys([*prompt.omitidos, *nuevo.omitidos]))
    nuevo.recortados = list(dict.fromkeys([*prompt.recortados, *nuevo.recortados]))
    nuevo.compresion = dict(prompt.compresion)
    return nuevo, {
        "incluido": incluido,
        "motivo": "incluido_completo" if incluido else "sin_espacio_para_paquete_completo",
        "tokens_estimados_antes": prompt.tokens_est,
        "tokens_estimados_despues": nuevo.tokens_est,
        "tokens_reales": None,
        "tipo_conteo": "estimacion_eq2_no_tokenizador",
    }
