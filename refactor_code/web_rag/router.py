from typing import List, Dict, Any, Optional
from .config import env_str
from .backends import google_cse, serpapi_google, tavily, naver_direct, serpapi_naver

def normalize_backend_alias(b: str) -> str:
    b = (b or "").strip().lower()
    return {
        "google":"google_cse", "googlecse":"google_cse",
        "serpapi_google":"serpapi", "google_serpapi":"serpapi",
        "naver":"serpapi_naver",
    }.get(b, b)

def resolve_backend_chain(engine_arg: Optional[str]) -> list[str]:
    eng = (engine_arg or env_str("WEB_SEARCH_ENGINE", default="auto")).strip().lower()
    if eng and eng != "auto":
        fallback = (env_str("SEARCH_BACKENDS", default="google_cse,naver_direct,serpapi_naver,serpapi,tavily"))
        chain = [normalize_backend_alias(eng)]
        for b in fallback.split(","):
            a = normalize_backend_alias(b.strip())
            if a and a not in chain: chain.append(a)
        return chain
    env_list = env_str("SEARCH_BACKENDS")
    if env_list:
        return [normalize_backend_alias(s) for s in env_list.split(",") if s.strip()]
    return ["google_cse","naver_direct","serpapi_naver","serpapi","tavily"]

def backend_call(key: str, query: str, *, num: int = 10) -> List[Dict[str, Any]]:
    key = (key or "").strip().lower()
    if key in ("google","google_cse"): return google_cse.search(query, num=num)
    if key in ("serpapi","serpapi_google"): return serpapi_google.search(query, num=num)
    if key in ("naver","serpapi_naver"): return serpapi_naver.search(query)
    if key == "naver_direct": return naver_direct.search(query, num=num)
    if key == "tavily": return tavily.search(query)
    return []
