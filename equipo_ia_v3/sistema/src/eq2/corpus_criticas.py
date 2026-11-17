"""V2-E.5-r2: corpus ETIQUETADO de deliberaciones para medir el clasificador de críticas.

Datos puros (sin E/S). Cada caso trae la CORRECCIÓN CONOCIDA, fijada a mano al escribir el caso
(no la decide el clasificador):
  verdad.objeciones           una entrada por objeción que el analizador DEBE encontrar, en orden:
                              True = la crítica es correcta, False = es falsa, None = no se sabe.
  verdad.objeciones_implicitas  críticas escritas en un formato que el analizador no puede extraer.
  verdad.solucion_final_correcta  si el texto final resuelve de verdad la tarea (juicio humano).
  verdad.contradiccion_real   si los agentes se contradicen de verdad.
Los textos imitan respuestas de un modelo pequeño; NO son salidas reales de Qwen.
"""

ENUNCIADO = "Escribe ordenar(xs) en Python; no debe modificar la lista de entrada."
MUTA = "```python\ndef ordenar(xs):\n    xs.sort()\n    return xs\n```"
BIEN = "```python\ndef ordenar(xs):\n    return sorted(xs)\n```"
BIEN_VACIA = "```python\ndef ordenar(xs):\n    if not xs:\n        return []\n    return sorted(xs)\n```"
INVIERTE = "```python\ndef ordenar(xs):\n    return xs[::-1]\n```"

CATEGORIAS = ("verdadera_con_evidencia", "falsa_con_cita_real", "evidencia_inexistente",
              "contradiccion_entre_agentes", "objecion_no_resuelta", "consenso_incorrecto",
              "formato_inesperado")

_AP = {"A1": "aprobar", "A2": "aprobar", "A3": "aprobar"}


def _caso(id_, cat, descripcion, propuesta, revision, replica, votos, objeciones, final_ok,
          contradiccion=False, implicitas=0, enunciado=ENUNCIADO):
    return {"id": id_, "categoria": cat, "descripcion": descripcion, "enunciado": enunciado,
            "propuesta": "Propuesta:\n" + propuesta + "\nFIN", "revision": revision, "replica": replica,
            "votos": dict(votos),
            "verdad": {"objeciones": list(objeciones), "objeciones_implicitas": implicitas,
                       "solucion_final_correcta": final_ok, "contradiccion_real": contradiccion}}


CASOS = (
    _caso("C01", "verdadera_con_evidencia", "crítica cierta con cita del código; se corrige",
          MUTA, "OBJECION: muta la lista de entrada | EVIDENCIA: `xs.sort()`",
          "ACEPTADA: uso sorted\n" + BIEN + "\nFIN", _AP, [True], True),
    _caso("C02", "verdadera_con_evidencia", "crítica cierta que cita el requisito; A1 la rebate y no corrige",
          MUTA, 'OBJECION: incumple el requisito | EVIDENCIA: "no debe modificar la lista"',
          "REBATIDA: ordenar en sitio es más rápido\n" + MUTA + "\nFIN", _AP, [True], False),
    _caso("C03", "falsa_con_cita_real", "crítica falsa con una cita que SÍ existe",
          BIEN, "OBJECION: muta la lista de entrada | EVIDENCIA: `sorted(xs)`",
          "REBATIDA: sorted devuelve una lista nueva\n" + BIEN + "\nFIN",
          {"A1": "aprobar", "A2": "aprobar", "A3": "aprobar_con_cambios"}, [False], True),
    _caso("C04", "falsa_con_cita_real", "crítica falsa con cita real; A3 rechaza y los demás aprueban",
          BIEN_VACIA, "OBJECION: falla con la lista vacía | EVIDENCIA: `if not xs`",
          "REBATIDA: la lista vacía devuelve []\n" + BIEN_VACIA + "\nFIN",
          {"A1": "aprobar", "A2": "aprobar", "A3": "rechazar"}, [False], True, contradiccion=True),
    _caso("C05", "evidencia_inexistente", "crítica falsa que cita un bucle que no existe",
          BIEN, "OBJECION: usa el método burbuja | EVIDENCIA: `for i in range(len(xs))`",
          "REBATIDA: no hay ningún bucle\n" + BIEN + "\nFIN", _AP, [False], True),
    _caso("C06", "evidencia_inexistente", "crítica falsa que cita una línea inexistente",
          BIEN, "OBJECION: variable sin definir | EVIDENCIA: línea 40",
          "REBATIDA: el código tiene 2 líneas\n" + BIEN + "\nFIN", _AP, [False], True),
    _caso("C07", "evidencia_inexistente", "crítica CIERTA con una cita parafraseada (no literal)",
          MUTA, "OBJECION: modifica la entrada | EVIDENCIA: `lista.sort()`",
          "REBATIDA: no existe lista.sort()\n" + MUTA + "\nFIN", _AP, [True], False),
    _caso("C08", "contradiccion_entre_agentes", "A3 dice «sin objeciones» y plantea una",
          BIEN, "SIN OBJECIONES: correcto\nOBJECION: falta documentar | EVIDENCIA: `def ordenar(xs)`",
          "ACEPTADA: añado docstring\n" + BIEN.replace("def ordenar(xs):", 'def ordenar(xs):\n    """Ordena."""')
          + "\nFIN", _AP, [None], True, contradiccion=True),
    _caso("C09", "contradiccion_entre_agentes", "sin objeciones, pero A2 rechaza y los demás aprueban",
          BIEN, "SIN OBJECIONES: probé [2, 1]", BIEN + "\nFIN",
          {"A1": "aprobar", "A2": "rechazar", "A3": "aprobar"}, [], True, contradiccion=True),
    _caso("C10", "objecion_no_resuelta", "A1 dice ACEPTADA pero deja el mismo código",
          MUTA, "OBJECION: muta la lista | EVIDENCIA: `xs.sort()`", "ACEPTADA: lo cambio\n" + MUTA + "\nFIN",
          _AP, [True], False, contradiccion=True),
    _caso("C11", "objecion_no_resuelta", "A1 no responde a la objeción y todos aprueban",
          MUTA, "OBJECION: muta la lista | EVIDENCIA: `xs.sort()`", MUTA + "\nFIN", _AP, [True], False,
          contradiccion=True),
    _caso("C12", "consenso_incorrecto", "código erróneo (invierte en vez de ordenar), nadie objeta",
          INVIERTE, "SIN OBJECIONES: correcto", INVIERTE + "\nFIN", _AP, [], False),
    _caso("C13", "consenso_incorrecto", "crítica cierta pero sin evidencia; se rebate y todos aprueban",
          INVIERTE, "OBJECION: no ordena, solo invierte", "REBATIDA: sí ordena\n" + INVIERTE + "\nFIN",
          _AP, [True], False),
    _caso("C14", "formato_inesperado", "OBJECIÓN con tilde, negritas y evidencia en la línea siguiente",
          MUTA, "**OBJECIÓN 1:** muta la lista de entrada\nEVIDENCIA: `xs.sort()`",
          "ACEPTADA: uso sorted\n" + BIEN + "\nFIN", _AP, [True], True),
    _caso("C15", "formato_inesperado", "respuesta en inglés con viñeta y evidencia entre paréntesis",
          MUTA, "- Objection: mutates the input (evidence: `xs.sort()`)",
          "ACEPTADA: uso sorted\n" + BIEN + "\nFIN", _AP, [True], True),
    _caso("C16", "formato_inesperado", "crítica cierta escrita en prosa, sin formato",
          MUTA, "Creo que la función modifica la lista original, habría que copiarla.",
          "ACEPTADA: uso sorted\n" + BIEN + "\nFIN", _AP, [], True, implicitas=1),
    _caso("C17", "formato_inesperado", "crítica cierta escrita como JSON",
          MUTA, '{"objecion": "muta la lista", "evidencia": "xs.sort()"}', MUTA + "\nFIN", _AP, [], False,
          implicitas=1),
    _caso("C18", "formato_inesperado", "revisión vacía", BIEN, "", BIEN + "\nFIN", _AP, [], True),
)
