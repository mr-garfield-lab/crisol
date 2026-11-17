from customs import check_address, calculate_fee

def pack_shipment(address):
    return address.strip()

def record_shipment(info):
    return info

def dispatch_shipment(address):
    address = pack_shipment(address)
    if not check_address(address):
        return None
    fee = calculate_fee(address)
    return record_shipment((address, fee))

def shipment_display_help():
    return "help"
