"""Perfiles explícitos; el crecimiento nunca modifica la ventana del modelo."""
PROFILES = {'compacto': 2000, 'modificar': 4000, 'auditar': 8000, 'profundo': 16000}


class BudgetError(ValueError):
    """El contenido obligatorio no cabe: se puede reintentar con más presupuesto."""


def generate_with_budget(builder, initial, *, auto=False, maximum=16000,
                         context_window=None, reserve_output=0, prompt_overhead=0):
    for name, value in [('budget', initial), ('max_budget', maximum),
                        ('reserve_output', reserve_output), ('prompt_overhead', prompt_overhead)]:
        if type(value) is not int or value < 0:
            raise ValueError(name + ' debe ser entero no negativo')
    if not 300 <= initial <= 1_000_000 or not 300 <= maximum <= 1_000_000:
        raise ValueError('Presupuesto debe estar entre 300 y 1000000')
    ceiling = maximum if auto else initial
    if context_window is not None:
        if type(context_window) is not int or context_window <= 0:
            raise ValueError('context_window debe ser entero positivo')
        available = context_window - reserve_output - prompt_overhead
        ceiling = min(ceiling, available)
    if initial > ceiling:
        raise BudgetError('Presupuesto inicial supera el techo o el espacio tras reservar prompt/respuesta')
    attempts, current = [], initial
    while True:
        attempts.append(current)
        try:
            result = builder(current)
        except BudgetError:
            if not auto or current >= ceiling:
                raise
        else:
            exhausted = any(str(x.get('reason', '')).startswith('budget') for x in result.get('omissions', []))
            if not (auto and exhausted and current < ceiling):
                result['budget_policy'] = {
                    'initial': initial, 'effective': current, 'maximum': ceiling,
                    'auto': auto, 'attempts': attempts, 'budget_exhausted': exhausted,
                    'context_window': context_window, 'reserve_output': reserve_output,
                    'prompt_overhead': prompt_overhead,
                    'unit': result['metrics']['budget_unit'],
                    'scope': 'texto entregado; reservas externas aportadas por el usuario',
                }
                return result
        current = min(ceiling, current * 2)
