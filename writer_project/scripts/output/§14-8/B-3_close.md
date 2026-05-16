# §14-8-B B-3 close — mystery 1+2 종결 박제

**측정 일자:** 2026-05-17
**commit chain:** `6a9e0dc` (commit 1 fix O) → `b0fae59` (commit 2 fix C) → `6e8f152` (commit 3 regression test) → 본 close commit (commit 4)
**미션:** §14-8-B mystery 1 (CHROMA_NAMESPACE_WEB=venfobel-vitamin-oa 회귀) + mystery 2 (vertex API model=gpt-4o → 404) 종결.

---

## § 1. 종결 박제

### 1-1. mystery 종결

| mystery | status | fix |
|---|---|---|
| **mystery 1**: wrapper subprocess CFG.CHROMA_NAMESPACE_WEB 가 `venfobel-vitamin-oa-web` 로 resolve | **★★★ resolved** | (O) protected env list — LLM_PROVIDER 보호 → cascading 차단 |
| **mystery 2**: wrapper subprocess vertex API call model=`gpt-4o` → 404 | **★★★ resolved** | (O) protected env list — LLM_MODEL 보호 → vertex_web_search L112 정상 model |

### 1-2. 적용 patch 요약

#### (O) protected env list — primary root cause fix (commit `6a9e0dc`)

`core/config.py`:
```python
_PROTECTED_ENV_KEYS = (
    "LLM_PROVIDER", "LLM_MODEL", "TOPIC_SLUG",
    "SKIP_VERTEX_SEARCH", "MIRROR_STATE_TO_ENV",
)

def reload_config_inplace() -> Config:
    global CFG
    with _cfg_lock:
        if _DOTENV_READY:
            _saved_env = {k: os.environ.get(k) for k in _PROTECTED_ENV_KEYS}
            try:
                load_dotenv(find_dotenv(usecwd=True), override=True)
            except Exception:
                pass
            for _k, _v in _saved_env.items():
                if _v is not None:
                    os.environ[_k] = _v
            _apply_provider_overlay(verbose=False)
            _apply_topic_preset(verbose=False)
        ...
```

#### (C) embedding dim mismatch 분리 log — wrapper safety net (commit `b0fae59`)

`agent/vector_search.py:_call_retrieve` — exception 의 mismatch signal 분리 log
`tools/web_rag/ingest_vector.py:1656-1671` — raise 직전 `[CHECK][embed-mismatch]` 명시 log

### 1-3. regression test 결과 (commit `6e8f152`)

- (a) protected key preservation: **PASS** (5/5)
- (b) 비-protected overlay cascading 차단: **PASS** (3/3)
- (c) end-to-end vertex_grounding: web_search returned tuple, no 404
- (d) dual-retrieve namespace 정합: topic-derived `ai-generated-creative-ad-platforms-web`, venfobel regression 부재

→ **FULL PASS ★★★**

---

## § 2. B-2ext4 deliverable 보강 박제 (minor)

`scripts/output/§14-8/B-2ext4_empirical_and_intent.md` § 1.3 의 ts 순서 박제 1줄 보강:
- 기존: "ts 순서: a (.4218) → c (.4350, Δ=13.2ms) → b (.4374, Δ=2.4ms from c). a→c→b 정합 (c 가 reload_config 내부, b 가 외부 직후)."
- 보강 정합: `c < b` (probe c 가 `_apply_provider_overlay` 직후, probe b 가 `reload_config()` 반환 후) — **call structure 정합** ★ (B-3 regression postfix 박제도 동일 순서 a < c < b 정합, 재현성 확인)

(별도 B-2ext4 doc 직접 수정은 close 자산 보전 위해 본 close summary 에 박제 — re-write 회피)

---

## § 3. mystery 진단 chain 종합 (B-1 → B-3)

| cycle | 박제 |
|---|---|
| B-1 (dual_retrieve namespace grep) | namespace 결정 logic + auto-derive 박제. mystery 식별 |
| B-1ext (mechanism grep) | (α)~(ε) hypothesis 5건 + (γ) 가장 유력 |
| B-2 (fix C patch design) | initial fix C 한계 박제 |
| B-2ext (F vertex 404 평가) | mystery 2 추가 (F-α~ζ), F-β 부분 기각 |
| B-2ext2 (자식 envdump) | STAGE_1/2 envdump → (γ) "기각 확정 (9번째 priors)" (★ measurement gap) |
| B-2ext3 (code-level mutate grep) | static-code 추론으로 단일 mechanism 박제 + (γ) 정정 |
| B-2ext4 (empirical confirmation) | in-chain probe a/c/b 로 stage flip 박제 + override=True 의도 (i)+(iii) 박제 + (γ) empirical reversal + CWD 의존성 박제 (priors 12), override 의도 박제 (priors 13) |
| **B-3 (fix + regression test)** | **(O)+(C) 적용 + regression test FULL PASS + mystery 종결** ★★★ |

### priors 정정 / 신규 누적 13건 → 본 close 시점:

1. case B 유력 → 기각
2. C timeout 의외로 유력 → 기각
3. D2 빠른 fail 예상 → 기각
4. driver wrapper #1/#2 高 의심 → 기각
5. vertex 404 gpt-4o (분기표 외) → 신규
6. chroma embedding mismatch (분기표 외) → 신규
7. fix C 추가 가치 (기존 handling 작동) → 부분 기각
8. (F-β) provider 분기 가장 유력 → 부분 기각 → 본 cycle env-level 정확화 (자연 해소)
9. (γ) .env.openai load — "기각 확정 (B-2ext2)" → ★ empirical reversal (B-2ext4)
10. (β) supervisor start_new_topic mutate path → 기각 (B-2ext3)
11. mystery 2건 단일 mechanism (B-2ext3 추론) → empirical CONFIRMED (B-2ext4)
12. CWD 의존성 (find_dotenv usecwd=True) → 신규 박제 (B-2ext4)
13. override=True 의도 (i) + (iii) hot-reload — 신규 박제 (B-2ext4)
14. audit 결과 의외 발견 잠재 후보 → 부재 박제 (B-3 audit)

---

## § 4. reserve list (defer 항목, §14-8 close 시 통합)

| 항목 | priority | 박제 |
|---|---|---|
| **CWD-independent .env resolution** | 中 | `find_dotenv(usecwd=True)` 가 CWD 의존. (O) 가 protected key 만 보호 → 비-protected key 의 CWD-dependent flip 잠재. e.g. ALLOWED_DOMAINS, LOG_LEVEL 등이 wrapper 환경에서 CWD 따라 다른 값. 별 진단 cycle 필요 |
| **다른 `reload_config()` 호출처 audit** | 中 | `tools/local_rag.py:252` (ensure_config_fresh, 1회 가드), `tools/web_rag/utils.py:168` (refresh_runtime_config), `app.py:2207,2282` (driver path). 현재 (O) 가 모든 호출처 적용되지만 driver path (app.py:2207) 가 driver 본인 의도와 충돌 가능 — 별 검증 |
| **protected list 외부화 / config 화** | 低 | 현재 module-level tuple 고정. 신규 driver-set env 추가 시 list 유지보수 필요. CFG dataclass field 또는 env var 화 가능 |
| **CHROMA_DIR 미보호 영향** | 低 | global `.env L121 =data/chroma_store` 가 wrapper pop 후 도입. driver pop 의도와 충돌 가능. 본 cycle empirical 영향 부재 박제 — 별 검증 reserve |
| **prior cycle 박제 자산 commit** | 中 | B-2ext2/B-2ext3/B-2ext_F/B-1ext/B-1/B-2 deliverable + scripts/diag/§14-8 다수 untracked. 별 commit 권장 (또는 §14-8 전체 close 시 일괄 commit) |

---

## § 5. 본 cycle 진단 가치 박제

- **시간 box 정합** — 4-commit sequence (~50 min)
- **mechanism 박제 → fix → regression test 의 self-contained chain** — B-2ext3 (static 추론) → B-2ext4 (empirical) → B-3 (audit+fix+regression) 의 진단 단계별 박제 자산
- **in-chain measurement protocol 자산화** — probe 삽입/revert/self-check (git diff empty) 표준화 ★
- **§12-20 hot-reload 의도 보존 + driver intent 보호 양립** — (O) snapshot/restore semantics 가 두 use case 동시 충족 ★

---

## § 6. §14-8-B close 결정

**§14-8-B mystery 1+2 종결 ★★★** — close 진입.

다음 분기:
- **(가) §14-8 전체 close** — §14-8-A (envdump-style mystery 진단 protocol 자산화) + §14-8-B (mystery 1+2 종결) 통합 close → reserve list 별 cycle 진입
- **(나) reserve 항목 즉시 진행** — CWD-independent .env resolution 등 우선순위 中 항목 별 cycle 진입
- **(다) 새 § 진입** — §12-13 (사용자 검증) 본 미션 복귀, 또는 다른 트랙

→ user 결정 대기 ★
