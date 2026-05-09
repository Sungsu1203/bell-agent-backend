# -*- coding: utf-8 -*-
"""§13-9 verification — ChatPromptTemplate 리팩터 + bind(temperature=0.1) 동작 확인.

검증:
  1. prompts.get_pptx_planner_prompt() 가 ChatPromptTemplate 반환
  2. format_messages({...}) 결과가 [SystemMessage, HumanMessage] 2개
  3. test.md 에 대한 plan_deck() 호출 성공 + 결과가 SlideDeckSpec
  4. (가능하면) bind 가 invoke 단계에 적용됐는지 로그 확인
"""
from __future__ import annotations
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from langchain_core.prompts import ChatPromptTemplate
from prompts import get_pptx_planner_prompt
from agent.export.planner import plan_deck


def check_template_structure() -> None:
    pt = get_pptx_planner_prompt()
    assert isinstance(pt, ChatPromptTemplate), f"expect ChatPromptTemplate, got {type(pt)}"
    msgs = pt.format_messages(
        slug="x", topic_title="X 토픽", md_text="# X\n\n본문",
        n_h2_chapters=0, n_h3_sections=0, n_total_slides=1,
    )
    assert len(msgs) == 2, f"expect 2 messages, got {len(msgs)}"
    assert msgs[0].type == "system", f"first msg type={msgs[0].type}"
    assert msgs[1].type == "human", f"second msg type={msgs[1].type}"
    print(f"[ok] ChatPromptTemplate 구조 정상")
    print(f"  system msg length: {len(msgs[0].content)} chars")
    print(f"  human msg length:  {len(msgs[1].content)} chars")
    print(f"  first 80 chars of system: {msgs[0].content[:80]}...")
    print(f"  first 80 chars of human:  {msgs[1].content[:80]}...")
    # 강제 규칙 키워드 system 안 존재 확인
    sys_text = msgs[0].content
    for kw in ["출력 언어는 모두 한국어", "TableSpec 으로 보존", "노트(`notes`)로 이동", "Few-shot"]:
        if kw not in sys_text:
            raise AssertionError(f"system msg missing keyword: {kw!r}")
    print(f"[ok] 강제 규칙 키워드 4종 모두 system 에 존재")


def quick_invoke() -> None:
    md = Path("reports/_cli_test/test.md").read_text(encoding="utf-8")
    print(f"\n[invoke] test.md ({len(md)} chars) → plan_deck (temp=0.1)")
    deck = plan_deck(md, slug="_cli_test", topic_title="CLI 합성 검증 — Vitamin B 시장 미니 리포트")
    print(f"[ok] slides={len(deck.slides)}")
    # 표 슬라이드 보존 여부 (test.md 에 1개 표 존재)
    table_count = sum(1 for s in deck.slides if s.table is not None)
    print(f"  table slides: {table_count} (expect 1)")
    # 첫 슬라이드 layout_id=0 확인
    print(f"  first slide layout_id: {deck.slides[0].layout_id} (expect 0)")
    # 한국어 비율 간단 확인
    for i, s in enumerate(deck.slides):
        kor = sum(1 for c in s.title if "가" <= c <= "힯")
        ttl_len = len([c for c in s.title if c.isalpha()])
        print(f"  S{i+1} layout={s.layout_id} title={s.title!r} (kor={kor}/{ttl_len})")


if __name__ == "__main__":
    check_template_structure()
    quick_invoke()
