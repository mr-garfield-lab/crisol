def approve_order(total, available):
    return total >= 0 and total <= available

def reject_order(reason):
    return {"accepted": False, "reason": reason}
