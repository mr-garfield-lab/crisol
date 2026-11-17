def cache_key(name):
    return name.strip().lower()

def cache_expired(entry):
    return not entry

def cache_fetch(name):
    key = cache_key(name)
    if cache_expired(key):
        return None
    return key

def cache_history_report():
    return []
