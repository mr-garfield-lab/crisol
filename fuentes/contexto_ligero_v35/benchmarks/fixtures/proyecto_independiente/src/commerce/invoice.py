from .contracts import validate_invoice

def applyInvoice(items):
    if not validate_invoice(items):
        return None
    return tuple(items)
