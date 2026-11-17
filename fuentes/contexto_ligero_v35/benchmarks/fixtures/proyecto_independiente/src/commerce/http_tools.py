def parseHTTPResponse(raw):
    status, body = raw.split(":", 1)
    return int(status), body

def encodeHTTPRequest(path):
    return "GET " + path
