import os, io, time, chardet, logging
from typing import List, Dict, Any
from .http import session
from .config import truthy
logger = logging.getLogger(__name__)

def load_web_page(url: str) -> str:
    connect_to = int(os.getenv("WEB_FETCH_TIMEOUT_CONNECT","6"))
    read_to    = int(os.getenv("WEB_FETCH_TIMEOUT_READ","20"))
    max_bytes  = int(os.getenv("WEB_FETCH_MAX_BYTES","1000000"))
    try:
        with session.get(url, timeout=(connect_to, read_to), stream=True) as r:
            r.raise_for_status()
            buf = io.BytesIO()
            for chunk in r.iter_content(8192):
                if chunk: buf.write(chunk)
                if buf.tell() >= max_bytes: break
            raw = buf.getvalue()
            enc = r.encoding or chardet.detect(raw).get("encoding") or "utf-8"
            text = raw.decode(enc, errors="replace")
            while "\n\n\n" in text or "\t\t\t" in text:
                text = text.replace("\n\n\n","\n\n").replace("\t\t\t","\t\t")
            return text.strip()
    except Exception as e:
        logger.debug("load_web_page failed for %s: %s", url, e); return ""

def enrich_raw_content(results: List[Dict[str, Any]]) -> None:
    top = int(os.getenv("WEB_SEARCH_RAW_FETCH_TOP","5") or "5")
    if top <= 0: return
    budget_s = float(os.getenv("WEB_FETCH_BUDGET_SECONDS","30"))
    t0 = time.time()
    def _bad(text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in ("access denied","enable javascript","just a moment","captcha","forbidden"))
    for i, r in enumerate(results):
        if i >= top or time.time() - t0 > budget_s: break
        if r.get("raw_content"): continue
        url = r.get("url");  if not url: continue
        html = load_web_page(url)
        if html and not _bad(html[:2000]):
            if any(m in html.lower() for m in ["__next_data__","static/chunks/","\"$\",\"html\""]):
                continue
            r["raw_content"] = html
