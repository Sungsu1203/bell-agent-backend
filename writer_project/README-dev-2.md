# README-dev (cont.) — §13-14-2 트랙 close 이후

## 이전 README-dev.md 와의 관계

본 파일은 `README-dev.md` 분량 임계 도달로 분리 운영된 후속 박제 파일.

- `README-dev.md` = §13-14-2 트랙 close (commit `612cc87`) 까지의 박제 자산 (~3296 줄)
- `README-dev-2.md` (본 파일) = `612cc87` 이후 신규 박제 자산
- cross-reference: `README-dev.md` 상단의 *트랙·catch 박제 인덱스* + 본문 catch 17·20·21·22·24·25·26 + §13-14 트랙 본문 참조

---

## 분리 운영 cut-off 시점

- HEAD (분리 직전) = `612cc87` (§13-14-2 트랙 close)
- 분리 commit hash = `08edfd7` (본 파일 신규 commit)
- 다음 박제 진입 시점 = 신규 트랙 (§13-8-3 Haiku 4.5 평가 또는 사용자 결정 다른 트랙)

---

## 트랙·catch 인덱스 (본 파일)

(이후 박제 진행 시 본 파일 안의 트랙·catch 위치 인덱스 추가 예정)

---

## 환경 상태 (분리 시점)

- `LLM_PROVIDER=anthropic`
- `ANTHROPIC_MODEL=claude-sonnet-4-6`
- `ANTHROPIC_REQUEST_TIMEOUT=600`
- `sections/venfobel-vitamin/` = gpt-4o 복원 상태
- Sonnet R3 backup = `reports/venfobel-vitamin/_sections_sonnet_R3_backup/` (1 명령 복원 가능)

---

## 다음 트랙 후보

- **(권고 1순위) §13-8-3** — Anthropic Haiku 4.5 평가 — dual track cost/latency trade-off 세분화, triple track 가능성
- **(권고 2순위) 다른 토픽 일반화 검증** — pet-food-premium / height-growth-supplement 등 (provider-agnostic + topic-agnostic 양상 확장)
- **(권고 3순위) §13-14-α-sonnet R2 prompt 패치** — Sonnet 4.6 의 §2 systematic 누락 양상 분석

---

## (이후 박제 진행 영역)

신규 트랙 진입 시 본 영역에 박제 시작.
