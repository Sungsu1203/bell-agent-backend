# §14-3 Phase 2 Step 2: `_rag_re` 매칭 검증 박제

## 1. 정규식 원문

**위치**: `agent/supervisor.py:609`

```python
_rag_re = r"(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)"
if re.search(_rag_re, last_text, flags=re.IGNORECASE):
    ...
    tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
```

### 구조 분석

3 그룹 순서 일치 (`group1 .*? group2 .*? group3`), `re.IGNORECASE` 적용:

| 그룹 | 멤버 | 의미 |
|---|---|---|
| group1 | 최신, 업데이트, update, latest | "갱신" 의도 키워드 |
| group2 | 자료, 리소스, 레퍼런스, 참고, sources, material | "자료" 명사 |
| group3 | rag, 벡터, vector, 임베딩, embedding, index, 색인, chroma | "인덱싱 대상" 키워드 |

세 그룹이 **순서대로** 등장해야 매칭. `.*?` lazy 라 분리 가능. 단어 사이에 임의 토큰 허용.

## 2. Candidate 매칭 결과

검증: `re.search(_rag_re, candidate, re.IGNORECASE)` (`.venv_vertex` python).

| # | 매칭 | groups | candidate |
|---|---|---|---|
| 1 | **TRUE** | ('최신', '자료', 'RAG') | `최신 자료로 RAG 업데이트해줘` |
| 2 | **TRUE** | ('최신', '자료', 'RAG') | `최신 자료로 RAG 업데이트` |
| 3 | **TRUE** | ('최신', '자료', 'RAG') | `최신 자료로 RAG 업데이트 부탁드립니다` |
| 4 | **TRUE** | ('업데이트', '자료', 'RAG') | `업데이트 자료 RAG` |
| 5 | **TRUE** | ('update', 'sources', 'RAG') | `update sources for RAG` |
| 6 | **TRUE** | ('latest', 'material', 'vector') | `latest material for vector index` |
| 7 | FALSE | - | `RAG 업데이트` |
| 8 | FALSE | - | `최신 정보로 RAG 업데이트` |
| 9 | FALSE | - | `자료 업데이트 RAG` |

### FALSE 원인 분석

- **#7** `RAG 업데이트`: group2 (자료/리소스/…) 누락 → 미매칭
- **#8** `최신 정보로 RAG 업데이트`: "정보" 는 group2 멤버 아님 → 미매칭
- **#9** `자료 업데이트 RAG`: group2 (자료) 가 group1 (업데이트) 보다 앞 → 순서 위반

### True positive 박제 가치

- candidate #1~#3 = 사용자 안내문 가이드 형식 (`communicator.py:735` "`최신 자료 보강 → 최신 자료로 RAG 업데이트`") 의 자연어 변형
- candidate #4~#6 = 순서 / 영어 / 동의어 변형 — 정규식 robustness 확인용
- supervisor `_rag_re` 가 매칭하는 패턴은 의외로 좁음 — group2 (자료/리소스/…) 누락 시 fast-path 우회

## 3. 최종 선정 명령어

```
최신 자료로 RAG 업데이트해줘
```

### 선정 근거

1. **`re.search(_rag_re, …)` TRUE** 검증 완료 (candidate #1, groups=('최신','자료','RAG'))
2. **사용자 안내문 가이드 형식과 정합** — `agent/communicator.py:735`:
   > `3) 최신 자료 보강 → 최신 자료로 RAG 업데이트`
3. **자연어 명령** — "...해줘" 어미가 multi-turn 진입 자연스러움
4. **graph 라우팅 보장** — supervisor `_rag_re` fast-path → `Task(agent="web_search_agent", description="rag_update:auto")` → web_search 노드 invoke (Phase 1 코드 리뷰 결론)
5. **vector path 우회 정합** — `agent/vector_search.py:1091-1094` 동일 정규식 매칭 시 검색 쿼리 → 빈 문자열, vector 우회 → web_search 단독 활성 (측정 시나리오로 깔끔)

### 백업 후보

- `최신 자료로 RAG 업데이트` (candidate #2, 어미 없음 단축형 — 동일 fast-path)

## 4. 다음 단계 (Step 3)

- 선정 명령어를 Step 3 Tier 2 dry-run 의 trigger 문자열로 사용
- 단, `_phase_b_run_inner.py` 의 명령어는 hard-coded — Step 4 에서 inner script 변경 시 본 명령어 박제
- Step 3 진입 시 driver `--trigger` flag 에 본 문자열 박제 (메타 박제 전용, inner 실행 명령어는 별도)
