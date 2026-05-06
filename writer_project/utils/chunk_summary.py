# utils/chunk_summary.py
"""
사이드카 .refs.json 의 marker → chunk 요약을 백그라운드로 생성.

§12-21 (사이드카 본체) 의 후속. 동기 LLM 호출로 섹션 write latency 가 늘어나는 것을 피하기 위해,
섹션 저장 직후 daemon thread 에서 병렬 LLM 호출 → 완료된 marker 부터 사이드카에 atomic merge.

운영 invariant:
- 메인 스레드가 섹션 저장 후 `start_background_summarization()` 만 호출하고 즉시 반환.
- 병렬 호출 결과는 `summary` 필드로 사이드카에 점진 추가. atomic rename 으로 reader race 차단.
- 서버 종료 시 daemon thread 가 같이 종료 — 부분 완료 사이드카는 다음 섹션 rewrite 시 재생성됨.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

# 사이드카 파일 동시 쓰기 직렬화 (per-process). 여러 섹션이 동시에 요약을 채우는 경우 contention 무시 수준.
_SIDECAR_LOCK = threading.Lock()

_MARKER_RE = re.compile(r"\[\[(\d+)\]\]")

# 요약 프롬프트 — 섹션 본문에서 [[N]] 등장 주변 ±N 자 + chunk 원본을 보고 1~3문장 요약.
_SUMMARY_PROMPT = """당신은 보고서의 인용 출처를 정제하는 어시스턴트입니다.

다음은 보고서 본문에서 인용 마커 [[N]] 가 등장한 주변 발췌입니다:
---
{section_context}
---

다음은 마커 [[N]] 이 가리키는 출처(chunk)의 원문입니다:
---
{chunk_text}
---

이 보고서가 출처에서 활용한 핵심 사실/주장만을 1~3문장의 한국어로 요약하세요.
- 보고서가 인용한 맥락에 직접 관련된 내용만.
- 출처 원문에만 있고 보고서가 활용하지 않은 부분은 제외.
- 요약 외 다른 텍스트(머리말·인용부호·"요약:" 같은 라벨) 금지.
"""


def extract_marker_context(gathered: str, marker: str, radius: int = 200) -> str:
    """
    gathered 본문에서 `[[<marker>]]` 가 등장한 첫 위치 주변 ±radius 자를 잘라 반환.
    여러 번 등장하면 첫 위치만 사용 (보통 marker 는 본문에서 1~2회 등장).
    """
    if not gathered or not marker:
        return ""
    needle = f"[[{marker}]]"
    idx = gathered.find(needle)
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(gathered), idx + len(needle) + radius)
    return gathered[start:end].strip()


def _summarize_one(llm: Any, chunk_text: str, section_context: str) -> str:
    """단일 LLM 호출. 실패 시 빈 문자열."""
    if not chunk_text.strip():
        return ""
    prompt = _SUMMARY_PROMPT.format(
        section_context=section_context or "(주변 발췌 없음)",
        chunk_text=chunk_text,
    )
    try:
        resp = llm.invoke(prompt)
        # langchain BaseChatModel: AIMessage(content=...) 반환. 다른 path 도 fallback.
        if hasattr(resp, "content"):
            txt = getattr(resp, "content")
        elif isinstance(resp, str):
            txt = resp
        else:
            txt = str(resp)
        return str(txt).strip()
    except Exception as e:
        logger.warning("[chunk_summary] LLM 호출 실패: %s", e)
        return ""


def _atomic_merge_summary(sidecar_path: Path, marker: str, summary: str) -> None:
    """사이드카 JSON 의 refs[marker]["summary"] 를 atomic 하게 갱신."""
    if not summary:
        return
    with _SIDECAR_LOCK:
        try:
            if not sidecar_path.exists():
                logger.debug("[chunk_summary] sidecar 사라짐 → skip merge: %s", sidecar_path)
                return
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            entry = data.get(marker)
            if not isinstance(entry, dict):
                return
            entry["summary"] = summary
            tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, sidecar_path)
        except Exception as e:
            logger.warning("[chunk_summary] sidecar atomic merge 실패 (marker=%s): %s", marker, e)


def _run_background(
    sidecar_path: Path,
    gathered: str,
    refs_map: Dict[str, Dict[str, Any]],
    max_workers: int = 4,
) -> None:
    """
    daemon thread 본체. refs_map 의 각 marker 에 대해 LLM 호출 → 사이드카 merge.
    LLM 은 lazy 로딩 (import 시점에 LangChain/Vertex 초기화 비용 회피).
    """
    try:
        from core.llm import get_llm
        llm = get_llm()
    except Exception as e:
        logger.warning("[chunk_summary] get_llm() 실패 → 요약 스킵: %s", e)
        return

    tasks: list[tuple[str, str, str]] = []  # (marker, chunk_text, section_context)
    for marker, entry in refs_map.items():
        chunk_text = (entry or {}).get("text") or ""
        if not chunk_text.strip():
            continue
        ctx = extract_marker_context(gathered, marker)
        tasks.append((marker, chunk_text, ctx))

    if not tasks:
        return

    logger.info("[chunk_summary] 백그라운드 요약 시작: %s (markers=%d)", sidecar_path.name, len(tasks))

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="chunk-summary") as ex:
        future_to_marker = {
            ex.submit(_summarize_one, llm, chunk_text, ctx): marker
            for (marker, chunk_text, ctx) in tasks
        }
        for fut in future_to_marker:
            marker = future_to_marker[fut]
            try:
                summary = fut.result(timeout=60)
            except Exception as e:
                logger.warning("[chunk_summary] marker=%s timeout/error: %s", marker, e)
                summary = ""
            if summary:
                _atomic_merge_summary(sidecar_path, marker, summary)

    logger.info("[chunk_summary] 백그라운드 요약 완료: %s", sidecar_path.name)


def start_background_summarization(
    sidecar_path: Path | str,
    gathered: str,
    refs_map: Mapping[str, Mapping[str, Any]],
) -> Optional[threading.Thread]:
    """
    섹션 저장 직후 호출. daemon thread 를 spawn 하고 즉시 반환.
    refs_map 빈 dict 또는 사이드카 부재 시 스킵.
    """
    p = Path(sidecar_path)
    if not refs_map:
        return None
    if not p.exists():
        logger.debug("[chunk_summary] sidecar 부재 → skip: %s", p)
        return None

    # dict copy (caller mutate 방지)
    snapshot: Dict[str, Dict[str, Any]] = {
        k: dict(v) for k, v in refs_map.items() if isinstance(v, Mapping)
    }
    if not snapshot:
        return None

    th = threading.Thread(
        target=_run_background,
        args=(p, gathered or "", snapshot),
        name=f"chunk-summary-{p.stem}",
        daemon=True,
    )
    th.start()
    return th
