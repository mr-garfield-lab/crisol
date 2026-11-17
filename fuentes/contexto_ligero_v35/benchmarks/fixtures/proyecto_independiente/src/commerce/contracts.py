def contract_total(items):
    return sum(item["amount"] for item in items)

def validate_invoice(items):
    if not items:
        raise ValueError("empty invoice")
    return contract_total(items) >= 0
