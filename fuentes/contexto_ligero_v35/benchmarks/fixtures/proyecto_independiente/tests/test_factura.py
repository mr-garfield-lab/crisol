from commerce.contracts import validate_invoice

def test_validar_factura():
    assert validate_invoice([{"amount": 5}])

def test_rechazar_factura_vacia():
    try:
        validate_invoice([])
    except ValueError:
        return
    raise AssertionError("expected refusal")
