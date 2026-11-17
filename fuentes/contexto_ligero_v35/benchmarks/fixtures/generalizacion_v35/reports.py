def parse_report(data):
    return data.strip()

def check_report(data):
    return bool(data)

def render_report(data):
    data = parse_report(data)
    if check_report(data):
        return data
    return ""

def help_report():
    return "help"
