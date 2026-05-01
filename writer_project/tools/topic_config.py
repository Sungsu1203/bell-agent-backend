# tools/topic_config.py
"""토픽별 설정 로더.

도메인 가중치/키워드 매핑처럼 "한 토픽 도메인에 맞춰 박힌" 값들을
topics/<slug>.config.json 으로 분리하여 관리한다.

사용:
    from tools.topic_config import get_domain_bonus_groups, get_xlsx_keyword_groups

설정 파일이 없거나 특정 키가 없으면 코드의 기본값을 사용 (현재 동작 호환).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 기본값 — 현재 하드코딩된 값을 그대로 옮긴 것 (호환 보장)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_DOMAIN_BONUS_GROUPS: list[dict[str, Any]] = [
    # file:// 프로토콜은 호스트가 아니라 별도 매칭 규칙
    {
        "name": "local",
        "score": 1.5,
        "match": "file_protocol",  # 특수 매칭: url.startswith("file://")
    },
    {
        "name": "pharma_media",
        "score": 1.0,
        "hosts": [
            "dailypharm.com", "medipana.com", "kpanews.co.kr",
            "yakup.com", "pharmnews.com", "medicopharma.co.kr",
            "healtho.co.kr",
        ],
    },
    {
        "name": "public_stats",
        "score": 0.8,
        "hosts": [
            "kosis.kr", "index.go.kr", "data.go.kr", "moef.go.kr",
            "mfds.go.kr", "hira.or.kr", "khidi.or.kr", "law.go.kr",
            "dart.fss.or.kr",
        ],
    },
    {
        "name": "penalties",
        "score": -0.5,
        "hosts": [
            "krx.co.kr", "financialreports.eu",
        ],
    },
]

_DEFAULT_XLSX_KEYWORD_GROUPS: dict[str, dict[str, Any]] = {
    "cost": {
        "score": 3,
        "keywords": [
            "광고비", "비용", "집행", "지출", "총액", "합계",
            "total", "sum", "spend", "cost",
        ],
    },
    "channel": {
        "score": 2,
        "keywords": [
            "디지털", "digital", "tv", "지상파", "케이블", "소셜",
            "search", "display", "youtube",
        ],
    },
    "summary": {
        "score": 2,
        "keywords": ["합계", "총"],
    },
    "currency": {
        "score": 1,
        "keywords": ["금액", "원"],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 로더
# ─────────────────────────────────────────────────────────────────────────────

# 캐시: (topic_slug) → loaded dict
_CACHE: dict[str, dict[str, Any]] = {}


def _topic_config_path(topic_slug: str) -> Path:
    """topics/<slug>.config.json 경로."""
    return Path("topics") / f"{topic_slug}.config.json"


def _resolve_topic_slug(topic_slug: Optional[str]) -> str:
    """인자로 주어진 슬러그가 없으면 환경변수에서 추론."""
    if topic_slug:
        return topic_slug.strip()
    return (os.getenv("TOPIC_SLUG") or "").strip()


def _load_raw(topic_slug: str) -> dict[str, Any]:
    """캐싱된 raw config 반환. 파일 없거나 에러면 빈 dict."""
    if topic_slug in _CACHE:
        return _CACHE[topic_slug]

    if not topic_slug:
        _CACHE[topic_slug] = {}
        return _CACHE[topic_slug]

    path = _topic_config_path(topic_slug)
    if not path.exists():
        _CACHE[topic_slug] = {}
        return _CACHE[topic_slug]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning(
                "[topic_config] %s is not a JSON object; ignoring", path
            )
            data = {}
        _CACHE[topic_slug] = data
        logger.info("[topic_config] loaded %s", path)
    except Exception as e:
        logger.warning("[topic_config] failed to load %s: %s", path, e)
        _CACHE[topic_slug] = {}

    return _CACHE[topic_slug]


def reset_cache() -> None:
    """테스트/리로드용 캐시 초기화."""
    _CACHE.clear()


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def get_domain_bonus_groups(topic_slug: Optional[str] = None) -> list[dict[str, Any]]:
    """도메인 가중치 그룹 리스트 반환.

    각 그룹은 다음 키를 가진다:
      - name: str (그룹명, 로깅/디버그용)
      - score: float (가중치)
      - hosts: list[str] (호스트명, 옵션)
      - match: str (특수 매칭 규칙, 옵션. 예: "file_protocol")
    """
    slug = _resolve_topic_slug(topic_slug)
    cfg = _load_raw(slug)
    raw = cfg.get("domain_bonus", {})
    groups = raw.get("groups") if isinstance(raw, dict) else None
    if isinstance(groups, list) and groups:
        return groups
    return _DEFAULT_DOMAIN_BONUS_GROUPS


def get_xlsx_keyword_groups(topic_slug: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """XLSX 메타 요약용 키워드 그룹 매핑 반환.

    각 그룹은 다음 키를 가진다:
      - score: int (점수)
      - keywords: list[str]
    """
    slug = _resolve_topic_slug(topic_slug)
    cfg = _load_raw(slug)
    raw = cfg.get("xlsx_keywords")
    if isinstance(raw, dict) and raw:
        return raw
    return _DEFAULT_XLSX_KEYWORD_GROUPS


__all__ = [
    "get_domain_bonus_groups",
    "get_xlsx_keyword_groups",
    "reset_cache",
]