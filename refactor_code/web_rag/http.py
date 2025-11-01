import os, requests, certifi
session = requests.Session()
session.headers.update({"User-Agent": os.getenv("USER_AGENT", "BookWriterBot/1.0")})
session.verify = certifi.where()

def http_get(url, **kw):
    kw.setdefault("timeout", (6, 20))
    return session.get(url, **kw)
