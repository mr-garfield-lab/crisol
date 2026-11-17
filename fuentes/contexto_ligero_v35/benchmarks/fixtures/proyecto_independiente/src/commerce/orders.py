from .policy import approve_order as permiso

def submitOrder(total, available):
    if not permiso(total, available):
        return None
    return {"total": total}

def cancel_order(order):
    return bool(order)
