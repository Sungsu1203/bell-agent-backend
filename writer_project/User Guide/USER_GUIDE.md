# Bell Agent 사용자 가이드 / User Guide

> **🔒 보안 안내 / Security Notice**
>
> 본 가이드와 Bell Agent 시스템은 **광고대행사 내부 자산**입니다. 외부 유출 시 클라이언트 NDA 위반 소지가 있으니 다음 사항을 반드시 준수해 주십시오.
>
> - **API key 보호** — `.env`, `.env.<provider>` 파일은 절대 외부 공유·Git commit·메신저 첨부 금지
> - **토픽 자산 보호** — `topics/*.env` 와 `refs/` 폴더 내 클라이언트 자료는 사내 저장소 외부 반출 금지
> - **산출물 보호** — 생성된 Word/PPT 보고서는 클라이언트 제안용 초안. 외부 공유 전 팀장·본부장 검토 필수
> - **개인 발급 API key** — 본인 명의 발급분은 본인 책임 하에 관리, 분실·노출 시 즉시 콘솔에서 revoke

---

## 머리말 / Preface

이 가이드는 광고기획·AE 분들이 **반복 업무에서 벗어나 가치 있는 일에 집중**할 수 있도록 만들어졌습니다. Bell Agent 는 자료 수집·목차 설계·초안 작성·검토 5단계를 자동화하여, 여러분이 전략적 판단과 클라이언트 커뮤니케이션에 더 많은 시간을 쓸 수 있게 합니다.

처음 30분만 투자하면 첫 보고서를 받아볼 수 있습니다. **(A) Quick Start** 를 차근차근 따라와 주세요.

---

## 목차 / Table of Contents

- [(A) Quick Start — 30분 안에 첫 보고서](#a-quick-start--30분-안에-첫-보고서--first-report-in-30-minutes)
  - [A-1. 사전 준비 / Prerequisites](#a-1-사전-준비--prerequisites)
  - [A-2. 소스 코드 설정 / Source Setup](#a-2-소스-코드-설정--source-setup)
  - [A-3. Backend 가동 / Run Backend](#a-3-backend-가동--run-backend)
  - [A-4. Frontend 가동 / Run Frontend](#a-4-frontend-가동--run-frontend)
  - [A-5. 첫 보고서 / Your First Report](#a-5-첫-보고서--your-first-report)
- **(B) 사용자 매뉴얼 / User Manual**
  - B-1. 시스템 구조 / System Architecture
  - B-2. 5단계 워크플로우 / 5-Step Workflow
  - B-3. 화면 구성 / UI Layout
  - B-4. 명령어 cheatsheet / Command Cheatsheet
  - B-5. LLM provider 선택 / LLM Provider Selection
  - B-6. 산출물 검증 / Output Validation
  - B-7. 토픽 추가 / Adding a New Topic
  - B-8. API key 직접 발급 / Issue Your Own API Keys
- **(C) FAQ + 트러블슈팅 / FAQ + Troubleshooting**
  - C-1. 자주 묻는 질문 / FAQ
  - C-2. 증상별 해결 / Symptom-based Troubleshooting
  - C-3. 박제 자산 / Reference Assets

---

# (A) Quick Start — 30분 안에 첫 보고서 / First Report in 30 Minutes

## A-1. 사전 준비 / Prerequisites

설치할 프로그램 4개. 모두 무료, Windows 공식 설치 파일로 진행합니다.

| 프로그램 | 버전 | 다운로드 | 용도 |
|---|---|---|---|
| **Python** | 3.12.x | [python.org/downloads](https://www.python.org/downloads/) | Backend 실행 환경 |
| **Node.js** | 20 LTS 이상 | [nodejs.org](https://nodejs.org/) | Frontend 실행 환경 |
| **Git** | 최신 | [git-scm.com](https://git-scm.com/download/win) | 소스 코드 받기 |
| **VS Code** | 최신 | [code.visualstudio.com](https://code.visualstudio.com/) | `.env` 편집 (메모장도 가능) |

**설치 시 체크포인트 / Installation checkpoints**

- **Python 설치 화면**: 맨 아래 `Add python.exe to PATH` 반드시 체크 ✅
- **Node.js 설치 화면**: 기본값 그대로 Next 진행
- **Git 설치 화면**: 기본값 그대로 Next 진행 (Editor 선택만 VS Code 권장)

**설치 검증 / Verify installation**

PowerShell 을 엽니다 (시작 메뉴 → `powershell` 검색 → `Windows PowerShell` 실행). 아래 4줄을 **한 줄씩** 복사·붙여넣기 하여 버전이 나오면 성공입니다.

```powershell
python --version
node --version
npm --version
git --version
```

예상 출력:
```
Python 3.12.x
v20.x.x
10.x.x
git version 2.x.x
```

> 💡 **PowerShell 사용 팁**
> - 명령어 붙여넣기: `Ctrl+V` 또는 마우스 우클릭
> - 명령 실행: `Enter`
> - 명령은 **한 줄씩 개별 실행** (여러 줄을 한 번에 붙여넣지 마세요)

---

## A-2. 소스 코드 설정 / Source Setup

### A-2-1. 작업 폴더 생성 / Create working folder

```powershell
mkdir C:\Bell_Agent
cd C:\Bell_Agent
```

### A-2-2. Backend 받기 / Clone backend

```powershell
cd C:\Bell_Agent
git clone https://github.com/Sungsu1203/bell-agent-backend.git backend
```

### A-2-3. Frontend 받기 / Clone frontend

```powershell
cd C:\Bell_Agent
git clone https://github.com/Sungsu1203/bell-agent-frontend.git frontend
```

### A-2-4. Backend Python 가상환경 구성 / Create Python venv

Quick Start 에서는 운영 default 인 **OpenAI 환경 하나만** 설치합니다. Vertex AI / Anthropic 추가 환경은 **B-5 LLM provider 선택** 챕터 참고.

```powershell
cd C:\Bell_Agent\backend

python -m venv .venv_openai
.\.venv_openai\Scripts\Activate.ps1
pip install -r requirements.openai.txt
deactivate
```

> ℹ️ `requirements.openai.txt` 는 `requirements.base.txt` 를 자동 포함합니다 (공통 의존성 → OpenAI 전용 추가). 3~5분 소요.

> ⚠️ **PowerShell 실행 정책 오류 시 / If you get execution policy error**
>
> `Activate.ps1` 실행 시 빨간 글씨로 오류가 나면 PowerShell 을 **관리자 권한**으로 다시 열고 아래 한 줄 실행 후 재시도:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### A-2-5. Frontend 패키지 설치 / Install frontend packages

```powershell
cd C:\Bell_Agent\frontend
npm install
```

3~5분 소요.

### A-2-6. 환경 파일 / Environment files

Backend `writer_project\` 폴더에 다음 파일들이 필요합니다.

**`.env`** (전역 설정 — LLM provider, 토픽 슬러그, 경로):

```dotenv
# ── LLM provider ──
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# ── 프로젝트 경로 ──
PROJECT_ROOT=C:\Bell_Agent\backend\writer_project

# ── 활성 토픽 ──
TOPIC_SLUG=venfobel-vitamin
```

> 💡 `TOPIC_SLUG` 는 `topics/<slug>.env` 의 파일명과 동일하게. 위 예시는 `topics/venfobel-vitamin.env` 프리셋이 자동 로드됨.

**`.env.openai`** (OpenAI API key — provider 별 분리 박제):

```dotenv
OPENAI_API_KEY=sk-...본인키...
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
```

> 📌 API key 본인 발급은 **B-8 API key 직접 발급** 챕터 참고. 팀장에게 받은 키를 그대로 사용해도 됩니다.

**`topics/venfobel-vitamin.env`** (토픽 프리셋)

이 파일은 팀장이 사내 채널로 별도 전달합니다. 클라이언트 NDA 자산이라 Git repo 에는 박제되어 있지 않습니다. 받은 파일을 `C:\Bell_Agent\backend\writer_project\topics\` 폴더에 그대로 복사하세요.

> 💡 새 토픽 추가는 **B-7 토픽 추가** 챕터 참고. `topics/_template.env.example` 을 복사해서 시작합니다.

**Frontend `.env.local`** (`frontend\` 폴더에 새로 생성):

```dotenv
NEXT_PUBLIC_BACKEND_PATH=C:\Bell_Agent\backend
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

**`refs/` 폴더 자료 / Reference files**

Backend 의 RAG (Retrieval-Augmented Generation) 가 학습할 클라이언트 자료를 `writer_project\refs\<topic_slug>\` 폴더에 배치합니다. 예:

```
C:\Bell_Agent\backend\writer_project\refs\venfobel-vitamin\
├─ 시장조사_2025.pdf
├─ 경쟁사_분석.docx
└─ 매출데이터.xlsx
```

> 💡 자료 배치 후에는 frontend Sidebar 의 **「최신 자료 갱신」** 버튼으로 RAG 인덱스를 업데이트합니다 (A-5-3 참고).

---

## A-3. Backend 가동 / Run Backend

PowerShell 창 **하나**를 열어둡니다 (가동 중에는 닫지 마세요).

```powershell
cd C:\Bell_Agent\backend
.\.venv_openai\Scripts\Activate.ps1
cd writer_project
$env:PYTHONIOENCODING="utf-8"
python app.py --serve --host 127.0.0.1 --port 8000
```

성공 시 다음과 같은 출력이 나옵니다:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

> 💡 **이 창을 닫으면 backend 가 멈춥니다.** 작업 내내 열어두세요.
>
> 종료 시: `Ctrl+C`

---

## A-4. Frontend 가동 / Run Frontend

**새 PowerShell 창**을 하나 더 열어서:

```powershell
cd C:\Bell_Agent\frontend
npm run dev
```

성공 시:
```
▲ Next.js 16.x
- Local:   http://localhost:3000
✓ Ready in 2.5s
```

이 창도 닫지 마세요.

---

## A-5. 첫 보고서 / Your First Report

### A-5-1. 브라우저 접속 / Open browser

Chrome 또는 Edge 에서:
```
http://localhost:3000
```

### A-5-2. 토픽 확인 / Verify active topic

화면 상단 Header 에 현재 활성 토픽의 제목이 표시됩니다. 예:
```
국내 프리미엄 비타민 시장 분석 — Venfobel (2025~2026)
```

이 제목이 작업 대상 토픽입니다. **frontend 에는 토픽 선택 UI 가 없습니다** — 토픽 전환은 backend `.env` 의 `TOPIC_SLUG` 를 변경 후 backend 를 재가동해야 합니다 (자세한 절차는 **B-7 토픽 추가**).

### A-5-3. 자료 학습 / Update RAG

좌측 Sidebar 「자료」 카드의 **「최신 자료 갱신」** 버튼 클릭.

두 가지 소스가 통합 임베딩됩니다:

- **로컬 자료 / Local RAG** — `refs/<topic_slug>/` 폴더와 하위 폴더의 PDF·PPTX·XLSX·MD·DOCX 파일 (`LOCAL_RAG_GLOBS` 박제값 적용)
- **웹 검색 / Web RAG** — Naver Search + Tavily Search 로 토픽 키워드 기반 검색, 수집된 문서를 동일 벡터스토어에 임베딩

파일 수와 웹 검색 결과 양에 따라 30초~3분 소요. 완료되면 Sidebar 「자료」 카드의 카운트가 `N개 파일 학습됨` 으로 갱신됩니다.

> 💡 ChatInput 에 `"최신 자료로 RAG 업데이트"` 같은 자연어로 입력해도 동일하게 동작합니다 (버튼은 이 명령의 단축 트리거).

### A-5-4. 워크플로우 진행 / Workflow progress

화면 중앙 상단의 **WorkflowStepper** 5단계는 backend state 의 진행 상황을 표시하는 **현황 UI** 입니다 (각 단계가 단일 명령어에 매핑되지는 않습니다):

```
1. 자료 준비  →  2. 미션 확인  →  3. 목차 설계  →  4. 섹션 집필  →  5. 검수·다운로드
   prepare        mission        outline         write           review
```

각 단계의 진행 조건은 다음과 같습니다:

| 단계 | 완료 조건 | 트리거 |
|---|---|---|
| **자료 준비** | `refs/` 자료 학습 완료 | A-5-3 「최신 자료 갱신」 |
| **미션 확인** | `BLOCKAGI_OBJECTIVE_1~3` 박제됨 | `topics/<slug>.env` 자동 로드 |
| **목차 설계** | outline 파일 생성됨 | ChatInput: `"목차 만들어줘"` |
| **섹션 집필** | 모든 섹션 작성 완료 | ChatInput: `write: <섹션제목>` |
| **검수·다운로드** | 검수 화면 진입 | WorkflowStepper 의 `검수·다운로드` 클릭 |

### A-5-5. 목차 생성 / Create outline

화면 하단의 **ChatInput** 에 아래와 같이 입력:

```
목차 만들어줘
```

또는 영문/축약 표현도 가능 (intent 매핑 동일):

```
outline
create outline
목차 생성
```

ChatResponsePanel 에 진행 메시지가 나오고, 완료되면 좌측 Sidebar 「목차」 카드에 섹션 목록이 표시됩니다.

### A-5-6. 섹션 작성 / Write sections

각 섹션을 작성하는 방법은 3가지:

**① ChatInput 에 명령 입력 (권장)**

```
write: 시장 분석
```

다른 섹션도 같은 방식으로:

```
write: 경쟁사 분석
write: 핵심 전략
```

**② Sidebar 의 ✏️ 버튼 클릭**

「목차」 카드의 각 섹션 우측에 ✏️ 아이콘. 클릭하면 해당 섹션이 자동 작성됩니다.

**③ 인덱스 명령**

```
1번 써줘
3번 작성
```

작성이 완료되면 ReportCanvas 에 본문이 표시되고, WorkflowStepper 의 **섹션 집필** 카운트가 `1 / 7`, `2 / 7` 식으로 진행됩니다.

### A-5-7. 검수 / Review

모든 섹션이 완료되면 WorkflowStepper 의 **검수·다운로드** 단계를 클릭. 우측 ReportCanvas 자리에 **ReviewPanel** 이 표시되어 보고서 전체 품질을 검토할 수 있습니다.

### A-5-8. 다운로드 / Download

Header 우측의 다운로드 버튼:

- **📄 Word (.docx)** — 보고서 본문
- **📊 PPT (.pptx)** — 프레젠테이션 (약 30초 소요, LogPanel 헤더에서 진행 상황 확인)

다운로드 폴더에 저장됩니다.

---

### ✅ Quick Start 완료 체크 / Completion checklist

- [ ] PowerShell 창 2개 (backend + frontend) 정상 가동 중
- [ ] 브라우저 `http://localhost:3000` 접속 성공
- [ ] Header 에 토픽 제목 정상 표시
- [ ] 「최신 자료 갱신」 으로 RAG 학습 완료 (local + web 양쪽)
- [ ] `"목차 만들어줘"` 로 목차 생성, Sidebar 에 섹션 목록 표시
- [ ] `write: <섹션제목>` 으로 모든 섹션 작성 완료
- [ ] Word + PPT 파일 다운로드 성공
- [ ] 파일 열어보고 내용 확인

여기까지 도달하셨다면 Bell Agent 가 정상 동작하는 것입니다. 🎉

본격 운영은 **(B) 사용자 매뉴얼**, 문제 발생 시 **(C) FAQ + 트러블슈팅** 챕터로 이동해 주세요.

---

# (B) 사용자 매뉴얼 / User Manual — Operations Reference

본 챕터는 Quick Start 를 마친 후 본격 운영 단계에서 참고하는 reference 입니다. 시스템 구조 이해 → 워크플로우 → 화면 구성 → 명령어 → provider 선택 → 산출물 검증 → 토픽 추가 → API key 발급 순서로 구성되어 있습니다.

---

## B-1. 시스템 구조 / System Architecture

Bell Agent 는 **frontend (Next.js)** ↔ **backend (FastAPI + LangGraph)** ↔ **외부 LLM·검색 API** 3-tier 구조로 동작합니다. 사용자가 알아야 할 동작 원리를 3개 도해로 박제합니다.

### B-1-1. 상위 구조 / Top-level architecture

테스터 PC 한 대 안에서 frontend·backend 가 모두 가동되고, 외부 LLM·검색 API 호출만 인터넷으로 나갑니다. **사내 LAN 으로 다른 동료 PC 에 영향 없음** — 각자 PC 에 독립 설치.

```
┌──────────────────────────── 테스터 PC (Windows) ────────────────────────────┐
│                                                                             │
│   ┌─────────────────────┐         HTTP          ┌──────────────────────┐    │
│   │                     │   /api/state          │                      │    │
│   │   Frontend          │ ◄─────────────────────│   Backend            │    │
│   │   (Next.js)         │   /api/run            │   (FastAPI +         │    │
│   │                     │   /api/export         │    LangGraph)        │    │
│   │   Browser UI        │ ─────────────────────►│                      │    │
│   │   localhost:3000    │   /api/cancel         │   localhost:8000     │    │
│   │                     │   /api/files          │                      │    │
│   └─────────────────────┘                       └──────────┬───────────┘    │
│         ▲                                                  │                │
│         │                                                  │                │
│         │ 브라우저 접속                                     │ 파일 I/O       │
│         │                                                  ▼                │
│   ┌─────┴───────────┐                            ┌──────────────────────┐   │
│   │  사용자          │                            │  로컬 파일시스템     │   │
│   │  (Chrome/Edge)  │                            │  - refs/<slug>/      │   │
│   └─────────────────┘                            │  - content/<slug>/   │   │
│                                                  │  - ChromaDB 인덱스   │   │
│                                                  │  - .env / topics/    │   │
│                                                  └──────────────────────┘   │
│                                                                             │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  │ HTTPS (외부 API 호출)
                                  │
                ┌─────────────────┼──────────────────┐
                ▼                 ▼                  ▼
        ┌──────────────┐   ┌──────────────┐  ┌──────────────┐
        │  LLM API     │   │  Embedding   │  │  Web Search  │
        │  - OpenAI    │   │  API         │  │  - Naver     │
        │  - Anthropic │   │  - OpenAI    │  │  - Tavily    │
        │  - Vertex AI │   │  3-large     │  │              │
        └──────────────┘   └──────────────┘  └──────────────┘
```

**핵심 박제 포인트**

- **frontend 와 backend 는 localhost 통신** — 인터넷 없이도 UI 는 뜸 (단, LLM·검색 호출은 인터넷 필요)
- **데이터는 모두 본인 PC 에 저장** — 보고서·자료·인덱스 모두 로컬. 클라우드 업로드 없음
- **외부 API 호출 시 데이터 전송** — 검색 키워드·LLM 프롬프트는 OpenAI/Anthropic/Google/Naver/Tavily 서버로 전송됨 (각 provider 의 데이터 정책 적용)

### B-1-2. Backend 내부 구조 / Backend internals

Backend 는 **LangGraph 기반 멀티에이전트 시스템** 입니다. 사용자 명령이 들어오면 **supervisor** 가 의도를 분석해서 적절한 agent 에게 분기시키고, 각 agent 는 ChromaDB (벡터DB) 와 LLM 을 호출해서 작업을 수행합니다.

```
                              사용자 명령
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │       Supervisor (분기)        │
                  │  명령 의도 파악 → agent 선택   │
                  └───────────────┬───────────────┘
                                  │
       ┌──────────┬───────────────┼───────────────┬──────────┐
       ▼          ▼               ▼               ▼          ▼
  ┌─────────┐ ┌─────────┐    ┌──────────┐    ┌────────┐ ┌──────────┐
  │ 자료    │ │ 웹검색  │    │ 목차     │    │ 섹션   │ │ 응답     │
  │ 검색    │ │         │    │ 설계     │    │ 작성   │ │ 정리     │
  │ Agent   │ │ Agent   │    │ Agent    │    │ Agent  │ │ Agent    │
  └────┬────┘ └────┬────┘    └────┬─────┘    └───┬────┘ └────┬─────┘
       │           │              │              │            │
       └─────┬─────┘              │              │            │
             ▼                    │              │            │
       ┌──────────────┐           │              │            │
       │  ChromaDB    │ ◄─────────┴──────────────┘            │
       │  (벡터 DB)   │                                       │
       │              │ ─────► 검색 결과                       │
       └──────┬───────┘                                       │
              │                                               │
              ▼                                               │
       ┌──────────────┐                                       │
       │   LLM API    │ ◄─────────────────────────────────────┤
       │ (provider별) │                                       │
       │              │ ─────► 생성 결과                       │
       └──────┬───────┘                                       │
              │                                               │
              ▼                                               ▼
       ┌──────────────┐                          ┌─────────────────┐
       │ 산출물 저장  │                          │ Frontend 응답   │
       │ content/     │                          │ /api/state JSON │
       │ <slug>/      │                          └─────────────────┘
       └──────────────┘
```

**6개 Agent 역할 박제 / 6 agents (코드명 병기)**

| Agent (사용자 친화) | 실제 노드명 (코드) | 역할 / Role | 트리거 명령 |
|---|---|---|---|
| **Supervisor** | `supervisor` | 명령 의도 파악, 다른 agent 로 분기 | (모든 명령의 진입점) |
| **자료 검색** | `vector_search_agent` | ChromaDB 에서 토픽 관련 문서 검색 | 작성 단계에서 자동 호출 |
| **웹 검색** | `web_search_agent` + `research_planner` + `research_synthesizer` | Naver / Tavily 로 최신 웹 자료 수집·정리 | RAG 갱신 / 자료 부족 시 |
| **목차 설계** | `content_strategist` | 토픽 미션 + 자료 기반 목차 생성 | `"목차 만들어줘"` |
| **섹션 작성** | `chapter_writer` + `section_writer` | 자료 인용 + LLM 으로 섹션 본문 작성 | `write: <섹션제목>` |
| **응답 정리** | `communicator` | 결과를 사용자에게 보여줄 형태로 가공 | (모든 작업 완료 후 자동) |

> 💡 **추상화 수준** — 위는 사용자가 알아야 할 동작 원리입니다. 실제 LangGraph 노드 구성·라우터 로직은 backend repo 의 `agent/`, `core/routers.py`, `graph.py` 코드 참조. 개발자용 상세는 `writer_project/README-dev.md` 박제.

### B-1-3. 데이터 흐름 / Data flow

사용자가 명령을 입력한 순간부터 화면에 결과가 표시되기까지의 전체 흐름.

```
 ① 사용자 입력 (ChatInput)
    "write: 시장 분석"
        │
        ▼
 ② Frontend → Backend
    POST /api/run
    { input: "write: 시장 분석" }
        │
        ▼
 ③ Backend Supervisor
    명령 파싱 → intent = "write"
    → 섹션 작성 Agent 호출
        │
        ▼
 ④ 자료 검색 (ChromaDB)
    "시장 분석" 관련 문서 추출
    → 인용 후보 7~10건
        │
        ▼
 ⑤ LLM 호출 (provider별)
    자료 + 토픽 미션 → LLM 프롬프트
    → 섹션 본문 생성
        │
        ▼
 ⑥ 결과 저장
    content/<topic_slug>/<섹션번호>-<섹션슬러그>.md
    + 인용 메타데이터
        │
        ▼
 ⑦ Frontend 폴링
    GET /api/state (3~5초 주기)
    → 새 섹션 감지
        │
        ▼
 ⑧ 화면 갱신
    Sidebar 「목차」 카드: ✓ 표시
    ReportCanvas: 본문 표시
    SourcePanel: 인용 자료 표시
    WorkflowStepper: "섹션 집필 1/7" → "2/7"
```

**핵심 API 엔드포인트 5개 / Core API endpoints**

테스터가 알아야 할 backend API 는 5개. (frontend 가 자동으로 호출하므로 직접 부를 일은 없지만, 트러블슈팅 시 참고)

| 엔드포인트 | 용도 | 호출 시점 |
|---|---|---|
| `GET /api/health` | backend 가동 확인 | 화면 로딩 시 1회 |
| `GET /api/state` | 현재 진행 상태 조회 (토픽·목차·섹션 진행도·current_provider) | 3~5초 주기 폴링 |
| `POST /api/run` | 자연어 명령 실행 (RAG 갱신, 목차 생성, 섹션 작성 등) | ChatInput 제출 / 「최신 자료 갱신」 클릭 |
| `POST /api/cancel` | 진행 중인 작업 취소 | LogPanel 의 ⛔ 버튼 |
| `POST /api/export` | Word / PPT 다운로드 | Header 의 📄 / 📊 버튼 |

> 💡 backend 가동 후 브라우저에서 `http://localhost:8000/docs` 접속 시 FastAPI 자동 문서로 전체 API 명세를 확인할 수 있습니다.

---

## B-2. 5단계 워크플로우 / 5-Step Workflow

Bell Agent 의 표준 작업 순서는 5단계입니다. WorkflowStepper 가 화면 중앙 상단에 항상 표시되어, 현재 어느 단계에 있는지를 한눈에 확인할 수 있습니다.

### B-2-1. 전체 흐름 / Overall flow

```
            ①              ②             ③              ④                ⑤
        ┌────────┐    ┌─────────┐   ┌──────────┐   ┌──────────┐    ┌──────────┐
        │ 자료   │ →  │ 미션    │ → │ 목차     │ → │ 섹션     │ →  │ 검수·    │
        │ 준비   │    │ 확인    │   │ 설계     │   │ 집필     │    │ 다운로드 │
        └────────┘    └─────────┘   └──────────┘   └──────────┘    └──────────┘

──────────────────────────────────────────────────────────────────────────────────
 사용자       │ refs/ 자료    │ topics/      │ "목차          │ write:        │ Stepper
 액션         │ 배치 +        │ <slug>.env   │  만들어줘"      │ <섹션제목>     │ ⑤ 클릭
              │ 「최신 자료    │ 자동 로드     │ 입력           │ 반복 입력      │ + 📄 / 📊
              │  갱신」 클릭   │              │                │                │ 다운로드
──────────────┼───────────────┼──────────────┼────────────────┼────────────────┼───────────
 Backend      │ Local RAG +   │ BLOCKAGI_    │ content_       │ chapter_       │ ReviewPanel
 처리         │ Web Search    │ OBJECTIVE_   │ strategist     │ writer +       │ 표시 +
              │ → ChromaDB    │ 1..N 박제    │ → outline      │ section_       │ /api/export
              │   임베딩      │              │   생성         │ writer         │ (docx/pptx)
──────────────┼───────────────┼──────────────┼────────────────┼────────────────┼───────────
 UI 변화      │ Stepper ① ✓   │ Stepper ② ✓  │ Stepper ③ ✓ +  │ Stepper ④      │ Stepper
              │ + 「자료」    │ + Sidebar    │ Sidebar        │ "1/7 → 7/7"    │ ⑤ ✓
              │ "N개 학습됨"  │ 「미션」      │ 「목차」        │ + ReportCanvas │ + ReviewPanel
              │              │ 카드 N개 표시 │ 카드 섹션 표시  │ 본문 표시      │ 화면 전환
──────────────┴───────────────┴──────────────┴────────────────┴────────────────┴───────────
 WorkflowStep   prepare         mission        outline          write            review
```

---

### B-2-2. ① 자료 준비 / Prepare

**입력** — `refs/<topic_slug>/` 폴더에 PDF·DOCX·PPTX·XLSX·MD 자료 배치 + Sidebar 「최신 자료 갱신」 버튼 클릭.

**Backend 처리** — Local RAG (`refs/<slug>/` 파일 임베딩) + Web Search (Naver + Tavily 토픽 키워드 검색) → ChromaDB 통합 벡터스토어 구축. `vector_search_agent` 와 `web_search_agent` 가 협업.

**출력** — Sidebar 「자료」 카드에 `N개 파일 학습됨` 카운트 갱신, ChromaDB 인덱스 디스크 저장.

**진입 조건** — `refs/<topic_slug>/` 폴더에 1개 이상 파일 존재 + backend 가동 중.

> 💡 자료 추가·교체 시마다 「최신 자료 갱신」 재실행 필요. 기존 인덱스는 자동 갱신되지 않습니다.

---

### B-2-3. ② 미션 확인 / Mission

**입력** — 별도 입력 불필요. `topics/<topic_slug>.env` 파일의 `BLOCKAGI_OBJECTIVE_1` ~ `BLOCKAGI_OBJECTIVE_N` (최대 10개) 항목이 backend 가동 시 자동 로드.

**Backend 처리** — `.env` 의 `TOPIC_SLUG` 를 읽고 → `topics/<slug>.env` 의 objective·title·기타 토픽별 설정을 `os.environ` 에 박제. 순서 보존 중복 제거 + JSON 배열 형태 `BLOCKAGI_OBJECTIVES` 도 통합 지원.

**출력** — Sidebar 「미션」 카드에 N개 objective 표시. Header 에 토픽 title 표시.

**진입 조건** — `topics/<topic_slug>.env` 파일에 `TOPIC_TITLE` + 최소 1개의 `BLOCKAGI_OBJECTIVE_*` 박제됨.

> 💡 **objective 박제 형식 자유** — 짧은 키워드도 가능, 서술형 장문도 가능. 예시:
> ```dotenv
> # 짧은 형태
> BLOCKAGI_OBJECTIVE_1=시장 규모·성장률
> BLOCKAGI_OBJECTIVE_2=경쟁사 포지셔닝
>
> # 서술형 (광고기획 권장 — 깊이 있는 보고서)
> BLOCKAGI_OBJECTIVE_1=일반의약품 종합비타민 시장 규모·성장률 추이(2020~2026)와 이중제형 건기식(오쏘몰 등)에 의한 카테고리 잠식 현황을 IQVIA·전자공시·OTC 인덱스 데이터로 정량 파악하고, 약국 채널 회복세·OTC 광고 사전심의 규제(허용/불가 표현, 약사 추천 광고 금지)를 반영한 메시지 가능 영역을 정의한다.
> ```
>
> 서술형이 길수록 LLM 이 더 구체적인 보고서를 산출합니다.

> 💡 미션을 수정하려면 `topics/<slug>.env` 편집 후 **backend 재가동** 필요 (`Ctrl+C` → 재시작). 운영 중 변경 불가.

---

### B-2-4. ③ 목차 설계 / Outline

**입력** — ChatInput 에 `"목차 만들어줘"` 또는 `"outline"` / `"create outline"` 입력.

**Backend 처리** — `content_strategist` agent 호출 → 토픽 미션 + RAG 자료 기반으로 섹션 구성 설계 → `outlines/<topic_slug>/outline_report.md` 파일 저장.

**출력** — Sidebar 「목차」 카드에 섹션 목록 표시 (예: `1. 시장 분석`, `2. 경쟁사 분석`, …).

**진입 조건** — ① 자료 준비 완료 + ② 미션 확인 완료 (objective 1개 이상 박제).

> 💡 목차 표시만 원하면 `"목차"` / `"show outline"` 입력 (기존 목차 재표시). 목차 재생성은 `"목차 만들어줘"` 다시 입력.

---

### B-2-5. ④ 섹션 집필 / Write

**입력** — ChatInput 에 `write: <섹션제목>` 또는 Sidebar 「목차」 카드의 섹션 ✏️ 버튼 클릭 또는 `"N번 써줘"` 인덱스 명령.

**Backend 처리** — `chapter_writer` + `section_writer` agent 호출 → `vector_search_agent` 가 ChromaDB 에서 관련 자료 추출 → LLM 으로 본문 생성·각주 박제 → `sections/<topic_slug>/<섹션슬러그>.md` 저장 (예: `sections/venfobel-vitamin/시장-분석.md`).

**출력** — ReportCanvas 에 본문 표시 + SourcePanel 에 인용 자료 칩 표시 + Stepper 「섹션 집필」 카운트 증가 (`1 / 7` → `2 / 7`).

**진입 조건** — ③ 목차 설계 완료.

> 💡 모든 섹션을 순차 작성 (`write: 1번` → `write: 2번` …) 또는 임의 순서 가능. 재작성하려면 동일 섹션에 대해 `write:` 명령 재실행 — 기존 파일이 **덮어쓰기** 되므로 좋은 버전이 나오면 외부 백업 권장.

---

### B-2-6. ⑤ 검수·다운로드 / Review & Download

**입력** — WorkflowStepper 의 ⑤ `검수·다운로드` 클릭 → ReviewPanel 진입 → Header 우측의 📄 Word / 📊 PPT 버튼 클릭.

**Backend 처리** — Review 단계는 frontend 화면 전환 + `/api/state` 진행도 표시. 다운로드 시 `report_builder.py` 가 `sections/<topic_slug>/*.md` 통합 → docx/pptx 변환 → `/api/export` 응답.

**출력** — 브라우저 다운로드 폴더에 `.docx` + `.pptx` 파일 저장.

**진입 조건** — ④ 섹션 집필 모든 섹션 완료 (`writeProgress.done === writeProgress.total`).

> 💡 PPT 변환은 약 30초 소요. LogPanel 헤더에서 진행 상황 확인 가능. 중간 취소는 LogPanel ⛔ 버튼.

---

### B-2-7. 비선형 흐름 / Non-linear flows

표준 5단계 외에 자주 발생하는 분기·반복 흐름.

**(a) 자료 부족 시 웹 검색 자동 보완 / Auto web search fallback**

```
④ 섹션 집필 중
     │
     ▼
writer pending + refs 비어있음 + RAG 준비 흔적 없음 감지
     │
     ▼
web_search_agent 자동 호출 (Naver + Tavily) — "단 1회" 룰
     │
     ▼
신규 자료 임베딩 → ChromaDB 보강 → 섹션 집필 재개
```

자료가 부족한 섹션에서 backend `router.tail` 로직이 **자동으로** 웹 검색을 호출합니다. 사용자 개입 불필요. 무한 루프 방지를 위해 동일 섹션 작성 사이클에서 **1회만** 자동 재시도. LogPanel 에 `web_search_agent` 호출이 표시됨.

> 💡 `SKIP_WEB_SEARCH=1` 환경변수가 설정되어 있으면 자동 웹 검색 우회 (vector_search_agent 로 직행).

**(b) 섹션 재작성 / Section rewrite**

```
④ 섹션 집필 완료
     │
     ▼
사용자: 결과 검토 → 재작성 결정
     │
     ▼
ChatInput: write: <동일 섹션제목>  (또는 Sidebar ✏️ 재클릭)
     │
     ▼
sections/<slug>/<섹션>.md 덮어쓰기 → ReportCanvas 갱신
```

기존 섹션 파일을 **덮어씁니다**. 이전 버전은 보존되지 않으므로 좋은 버전이 나오면 외부에 백업 권장.

**(c) RAG 재갱신 / RAG refresh**

```
④ 또는 ⑤ 진행 중
     │
     ▼
사용자: refs/<slug>/ 폴더에 신규 자료 추가
     │
     ▼
Sidebar 「최신 자료 갱신」 클릭 (또는 "최신 자료로 RAG 업데이트" 입력)
     │
     ▼
ChromaDB 인덱스 재구축 (기존 + 신규) → 이후 섹션 집필에 반영
```

이미 작성된 섹션에는 영향 없음. 갱신 **이후에** 작성되는 섹션부터 새 자료 반영.

---

## B-3. 화면 구성 / UI Layout

Bell Agent 의 화면은 **상단 영역** (Header + WorkflowStepper) + **메인 영역** (Sidebar + 본문 + 우측 패널) + **하단 영역** (LogPanel) 의 3단 구조입니다. 우측 패널은 사용자 액션에 따라 동적으로 열림·닫힘.

### B-3-1. 전체 화면 영역 / Screen layout

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ ① Header                                                                       │
│    토픽 title · 가동 상태 · 📄 Word · 📊 PPT 다운로드                            │
├────────────────────────────────────────────────────────────────────────────────┤
│ ② WorkflowStepper                                                              │
│    ① 자료 준비 → ② 미션 확인 → ③ 목차 설계 → ④ 섹션 집필 → ⑤ 검수·다운로드     │
├──────────────┬──────────────────────────────────────┬──────────────────────────┤
│              │                                      │                          │
│ ③ Sidebar    │   ④ ReportCanvas (Write 모드)        │   ⑥ ChatResponsePanel   │
│   (240px)    │      또는                            │      또는                │
│              │   ⑤ ReviewPanel (Review 모드)        │   ⑦ SourcePanel          │
│ ┌─────────┐  │                                      │   (360px, 조건부)        │
│ │ 자료     │  │   ┌────────────────────────────┐    │                          │
│ │ N개 학습 │  │   │ 섹션 제목                  │    │   ⑥ ChatResponsePanel:  │
│ │ 최신갱신 │  │   │                            │    │      마지막 명령 결과     │
│ └─────────┘  │   │ 본문 (Markdown 렌더)        │    │      + 토글 ✕            │
│ ┌─────────┐  │   │ - 각주 [1] [2] (클릭 가능)  │    │                          │
│ │ 목차     │  │   │ - 인용 칩                  │    │   ⑦ SourcePanel:        │
│ │ 1. ...   │  │   │                            │    │      클릭한 인용 자료의   │
│ │ 2. ... ✏ │  │   └────────────────────────────┘    │      원문 미리보기        │
│ │ 3. ... ✏ │  │                                      │      + 출처 URL          │
│ └─────────┘  │   ┌────────────────────────────┐    │                          │
│ ┌─────────┐  │   │ ChatInput                  │    │   ※ 동시 표시 불가 —     │
│ │ 미션     │  │   │ ───────────────────────── │    │     명령 실행이 출처      │
│ │ • OBJ1   │  │   │ [          ]    [Run ▶]   │    │     보기보다 우선         │
│ │ • OBJ2   │  │   └────────────────────────────┘    │                          │
│ │ • OBJ3   │  │                                      │                          │
│ └─────────┘  │                                      │                          │
│ ┌─────────┐  │                                      │                          │
│ │ Settings │  │                                      │                          │
│ │ openai   │  │                                      │                          │
│ │ gpt-4o   │  │                                      │                          │
│ └─────────┘  │                                      │                          │
│              │                                      │                          │
├──────────────┴──────────────────────────────────────┴──────────────────────────┤
│ ⑧ LogPanel  [▲ 펼치기]   running... · ⛔ 취소                                 │
└────────────────────────────────────────────────────────────────────────────────┘

 그리드 구조: 240px / 1fr / 360px(조건부)
 우측 패널 미오픈 시: 240px / 1fr  (ReportCanvas 가 가로 폭 확장)
```

### B-3-2. 각 영역 상세 / Region details

**① Header — 상단 고정 / Top bar**

- **위치**: 화면 최상단 (전체 가로 폭)
- **표시 내용**: 현재 활성 토픽의 title (Quick Start A-5-2 참고), backend 가동 상태 인디케이터
- **사용자 액션**: 우측의 📄 Word / 📊 PPT 버튼 클릭 → 보고서 다운로드 (A-5-8 참고)
- **참고**: 토픽 전환은 frontend 에서 불가, backend `.env` 의 `TOPIC_SLUG` 변경 후 재가동 필요 (B-7 토픽 추가 참고)

**② WorkflowStepper — 진행 상태 표시 / Step indicator**

- **위치**: Header 아래, 메인 영역 위
- **표시 내용**: 5단계 진행 상태 (현재 단계 / 완료 단계 / 대기 단계) + 단계별 보조 텍스트 (예: `섹션 집필 3 / 7`)
- **사용자 액션**: 완료(`done`) 또는 현재(`current`) 단계만 클릭 가능. ⑤ `검수·다운로드` 클릭 시 ReviewPanel 화면 전환
- **참고**: 단계 클릭은 명령 실행이 아닌 **화면 전환만** (B-2-1 참고)

**③ Sidebar — 좌측 4개 카드 / Left sidebar (240px)**

- **위치**: 메인 영역 좌측, 고정 폭 240px
- **표시 내용**: 4개 카드 박제
  - 「자료」 — 학습된 파일 수 + 「최신 자료 갱신」 버튼 + 마지막 갱신 시각
  - 「목차」 — 섹션 목록 (id · title · 상태 아이콘 · ✏️ 작성 버튼)
  - 「미션」 — `BLOCKAGI_OBJECTIVE_*` 항목 (긴 서술형은 첫 명사구만 표시, hover 시 tooltip 으로 전문)
  - 「Settings」 — 현재 LLM provider + model 표시 (예: `openai / gpt-4o`)
- **사용자 액션**: 「최신 자료 갱신」 클릭 (RAG 갱신), 섹션 ✏️ 클릭 (해당 섹션 작성), 섹션 행 클릭 (해당 섹션을 ReportCanvas 에 표시), Settings 카드 클릭 (변경 가이드 모달 — B-5 참고)

**④ ReportCanvas — 본문 + ChatInput 통합 영역 / Main canvas (Write mode)**

- **위치**: 메인 영역 중앙 (가로 폭 가변 1fr)
- **표시 내용**: 상단에 선택된 섹션의 제목 + 본문 (Markdown 렌더), 하단에 ChatInput (명령 입력 필드 + [Run ▶] 버튼)
- **사용자 액션**: 본문 내 각주 번호 `[1]` `[2]` 클릭 → SourcePanel 에 해당 인용 자료 표시. ChatInput 에 자연어 명령 입력 → 백엔드 `/api/run` 호출 → ChatResponsePanel 에 결과 표시
- **참고**: ⑤ `검수·다운로드` 단계 클릭 시 이 영역이 ReviewPanel 로 교체됨 (xor)

**⑤ ReviewPanel — 검수 화면 / Review mode**

- **위치**: ReportCanvas 와 동일 위치 (Write ↔ Review 토글)
- **표시 내용**: 보고서 전체 품질 검토 결과 (review 단계의 backend state 기반)
- **사용자 액션**: 검수 내용 확인 → Header 의 📄 Word / 📊 PPT 다운로드 진행
- **참고**: WorkflowStepper 의 ⑤ 단계가 클릭 가능해야 진입 (모든 섹션 작성 완료 시)

**⑥ ChatResponsePanel — 우측 명령 응답 패널 / Right panel: command response (360px, 조건부)**

- **위치**: 메인 영역 우측, 폭 360px, 명령 실행 시에만 표시
- **표시 내용**: 마지막 ChatInput 명령의 query + 실행 상태 (loading / ok / error) + 응답 메시지
- **사용자 액션**: 우상단 ✕ 클릭 → 패널 닫기 (메인 영역 가로 폭 복원)
- **참고**: 새 명령 실행 시 자동으로 다시 열림. SourcePanel 과 동시 표시 불가 (chat 우선)

**⑦ SourcePanel — 우측 인용 자료 패널 / Right panel: source preview (360px, 조건부)**

- **위치**: 메인 영역 우측, 폭 360px, 본문 인용 칩 클릭 시에만 표시
- **표시 내용**: 클릭한 인용 자료의 원문 미리보기 + 출처 URL / 파일명 + 도메인 정보
- **사용자 액션**: URL 클릭 → 새 탭으로 원문 확인. 우상단 ✕ 클릭 → 패널 닫기
- **참고**: 새 명령 실행 시 ChatResponsePanel 우선 표시로 자동 닫힘. ChatResponsePanel 닫은 후 인용 칩 다시 클릭하면 SourcePanel 표시

**⑧ LogPanel — 하단 로그 / Bottom log (collapsible)**

- **위치**: 화면 최하단 고정, 기본 접힘 상태 (높이 44px)
- **표시 내용**: 접힘 시 — 현재 실행 중 작업 요약 (예: `web_search_agent running...`) + ⛔ 취소 버튼. 펼침 시 — backend `/api/logs` 의 시간순 로그 스트림 (`/api/events` 폴링)
- **사용자 액션**: 헤더 클릭 → 펼치기/접기. ⛔ 버튼 클릭 → `/api/cancel` 호출 (진행 중 작업 취소)
- **참고**: 트러블슈팅 시 펼침 모드로 사용. 에러 발생 시 빨간 로그가 자동 표시됨 (C-2 트러블슈팅 참고)

### B-3-3. 화면 상태 전환 / Screen state transitions

세 가지 모드가 자동/수동으로 전환됩니다.

| 모드 | 트리거 | 메인 영역 | 우측 패널 |
|---|---|---|---|
| **기본 모드** | 초기 진입 / 패널 닫기 | ReportCanvas | (없음) |
| **명령 모드** | ChatInput 제출 / 「최신 자료 갱신」 클릭 | ReportCanvas | ChatResponsePanel |
| **출처 모드** | 본문 각주 / 인용 칩 클릭 | ReportCanvas | SourcePanel |
| **검수 모드** | WorkflowStepper ⑤ 클릭 | ReviewPanel | (없음) |

> 💡 우측 패널은 **한 번에 하나만**. ChatResponsePanel 과 SourcePanel 동시 표시 불가 — 명령 실행이 출처 보기보다 더 최근 상호작용이라 ChatResponsePanel 이 우선합니다.

---

## B-4. 명령어 cheatsheet / Command Cheatsheet

Bell Agent 의 모든 명령은 **자연어 1개 입력 필드 (ChatInput)** 로 통합되어 있습니다. backend 의 `parse_command_intent()` 가 입력 문자열을 9가지 intent 중 하나로 분류해서 처리.

### B-4-1. 핵심 명령 9종 / Core commands

| # | Intent | 자연어 예시 / Trigger phrases | 동작 / Effect |
|---|---|---|---|
| 1 | **`rag_update`** | `최신 자료로 RAG 업데이트`<br>`최신 자료 갱신`<br>`update sources to RAG` | `refs/` 자료 + Naver/Tavily 웹 검색 → ChromaDB 임베딩. Sidebar 「자료」 카드 카운트 갱신. |
| 2 | **`create_outline`** | `목차 만들어줘`<br>`목차 생성`<br>`outline 새로 작성` | `content_strategist` agent 호출 → `outlines/<slug>/outline_report.md` 생성. Sidebar 「목차」 카드에 섹션 목록 표시. |
| 3 | **`show_outline`** | `목차`<br>`목차 보여줘`<br>`outline`<br>`show outline` | 기존 목차 재표시 (재생성 없이). 「목차」 카드만 갱신. |
| 4 | **`write`** | `write: 시장 분석`<br>`작성: 시장 분석`<br>`집필: 시장 분석` | 명시형. `chapter_writer` + `section_writer` 호출 → `sections/<slug>/<섹션슬러그>.md` 저장. ReportCanvas 에 본문 표시. |
| 5 | **`write_index`** | `1. 시장 분석`<br>`1) 시장 분석`<br>`4번 써줘`<br>`3번 작성해주세요` | 인덱스형. 목차의 N번째 섹션을 자동으로 찾아 작성. |
| 6 | **`build_report`** | `build: report`<br>`보고서 빌드`<br>`최종 보고서 생성` | 모든 섹션 통합 → docx 빌드. (Header 의 📄 Word 다운로드와 유사하지만 명시 트리거.) |
| 7 | **`new_topic`** | `새 보고서: 비타민 시장`<br>`주제 변경: 화장품 트렌드`<br>`new report: ...`<br>`switch topic: ...` | 새 토픽으로 전환 (제목 추출). 본격 토픽 추가는 B-7 참고. |
| 8 | **`force_queries`** | `force_query: 2025 종합비타민 시장 규모` | 검색 쿼리 강제 지정 — RAG 자료 부족 시 특정 키워드로 웹 검색 강제. |
| 9 | **`none`** | (위 패턴 미매칭 시) | 일반 QA 로 처리. RAG 검색 후 LLM 응답. |

> 💡 **매칭은 정규식 기반** — 따옴표·존댓말·영문 대소문자 혼용 모두 허용. 예: `"write: 시장 분석"`, `'작성: 시장 분석'`, `WRITE: 시장 분석` 모두 동일 인식.

### B-4-2. 단축 버튼 매핑 / Shortcut button mapping

자주 쓰는 명령은 UI 버튼으로 매핑되어 있어 입력 없이도 실행 가능.

| 위치 / Location | 버튼 | 동등 자연어 명령 |
|---|---|---|
| Sidebar 「자료」 카드 | **최신 자료 갱신** | `최신 자료로 RAG 업데이트` |
| Sidebar 「목차」 카드 → 섹션 우측 | **✏️ 작성** | `write: <해당 섹션제목>` |
| Header 우측 | **📄 Word** | `/api/export?format=docx` 직접 호출 (자연어 없음) |
| Header 우측 | **📊 PPT** | `/api/export?format=pptx` 직접 호출 (자연어 없음) |
| LogPanel 헤더 | **⛔ 취소** | `/api/cancel` 직접 호출 |
| WorkflowStepper ⑤ | **검수·다운로드** | 화면 전환만 (명령 아님) |

### B-4-3. 본문 내 상호작용 / In-canvas interactions

ReportCanvas 본문에서 클릭 가능한 요소들.

| 요소 / Element | 표시 | 클릭 시 동작 |
|---|---|---|
| **각주 번호** | `[1]` `[2]` | SourcePanel 열림 → 해당 인용 자료 원문 미리보기 + 출처 URL |
| **인용 칩** | `🔗 IQVIA 2024` | 동일 — SourcePanel 열림 |
| **섹션 행 (Sidebar)** | `1. 시장 분석` | 해당 섹션을 ReportCanvas 에 표시 (write 명령 아님, 표시 전환만) |
| **각주 정의** | 본문 하단의 `[1] ...` | (정적 표시, 클릭 동작 없음) |

> 💡 SourcePanel 우상단 ✕ 클릭으로 닫기. 새 ChatInput 명령 실행 시 SourcePanel 은 자동으로 ChatResponsePanel 로 교체됨 (B-3-3 화면 상태 전환 참고).

### B-4-4. 자주 쓰는 시나리오 / Common scenarios

**시나리오 A — 첫 보고서 풀 사이클**

```
1. (Sidebar) 「최신 자료 갱신」 클릭                ← rag_update
2. (ChatInput) "목차 만들어줘"                      ← create_outline
3. (Sidebar) 섹션 1 ✏️ 클릭                        ← write
4. (Sidebar) 섹션 2 ✏️ 클릭                        ← write
   ... (모든 섹션 반복)
5. (Stepper) ⑤ 검수·다운로드 클릭                  ← review 화면 전환
6. (Header) 📄 Word + 📊 PPT 다운로드               ← /api/export
```

**시나리오 B — 특정 섹션만 재작성**

```
1. (Sidebar) 재작성할 섹션 ✏️ 다시 클릭             ← write (덮어쓰기)
   또는
1. (ChatInput) "write: 시장 분석"                   ← write (덮어쓰기)
```

**시나리오 C — 자료 부족 섹션에 키워드 강제 검색**

```
1. (ChatInput) "force_query: 2025 종합비타민 시장 IQVIA"  ← force_queries
   → 해당 키워드로 Naver/Tavily 강제 검색 → ChromaDB 보강
2. (ChatInput) "write: 시장 분석"                          ← write
```

**시나리오 D — 보고서 작성 중 새 자료 추가**

```
1. (Windows 탐색기) refs/<slug>/ 폴더에 PDF 추가
2. (Sidebar) 「최신 자료 갱신」 클릭                ← rag_update
   → 기존 인덱스 + 신규 자료 통합
3. (ChatInput) "write: <섹션제목>"                  ← write (신규 자료 반영)
```

---

## B-5. LLM provider 선택 / LLM Provider Selection

Bell Agent 는 5개 LLM provider 를 지원합니다. 운영 default 는 OpenAI (gpt-4o) 이며, 토픽 성격·예산·시간에 따라 변경 가능합니다.

### B-5-1. 지원 provider 5종 / Supported providers

| Provider | 모델 | 특성 | 비용 (참고) | 평균 시간 (참고) | 권장 용도 |
|---|---|---|---|---|---|
| **OpenAI** | `gpt-4o` | 운영 default · 빠름 · 균형 | ~$0.12 | 35–172s | 일상 보고서 (기본 선택) |
| **Anthropic Sonnet 4.6** | `claude-sonnet-4-6` | 상세 · 고비용 · 결정성 높음 | ~$0.44 | 317s | 핵심 클라이언트 제안서, 깊이 있는 분석 |
| **Anthropic Haiku 4.5** | `claude-haiku-4-5-20251001` | 저렴 · 빠름 · 출력량 풍부 | ~$0.13 | 140s | 다량 초안 생성, 빠른 반복 작업 |
| **Vertex AI** | `gemini-2.5-flash` | Google 인프라 · 한국어 강함 | 측정 예정 | 측정 예정 | 한국어 자료 비중 높은 토픽 |
| **Gemini (Google AI Studio)** | `gemini-2.5-pro` | API key 방식 (Vertex 와 별도) | 측정 예정 | 측정 예정 | 개별 테스트 용도 (frontend 미노출) |

> 💡 비용·시간은 venfobel-vitamin 토픽 1회 풀 사이클 (자료 갱신 → 목차 → 7섹션 작성 → docx 빌드) 기준 측정값. 토픽 자료량·섹션 수에 따라 변동.

> ⚠️ **Gemini (Google AI Studio) 는 frontend Settings 카드에 노출되지 않습니다** — 변경하려면 backend `.env` 의 `LLM_PROVIDER=gemini` 를 직접 편집해야 합니다.

### B-5-2. Settings 카드 / Settings card

Sidebar 의 4번째 카드 「설정 / Settings」 에서 현재 활성 provider 를 확인하고 변경 가이드를 호출할 수 있습니다.

```
┌──────────────────────────┐
│ 설정 / SETTINGS          │
├──────────────────────────┤
│ 현재 활성 / Active        │
│ ┌──────────────────────┐ │
│ │ ● OpenAI (gpt-4o)    │ │
│ │   운영 default · 빠름 │ │
│ └──────────────────────┘ │
│                          │
│ 변경 / Switch to         │
│ ○ Anthropic (Sonnet 4.6) │
│ ○ Anthropic (Haiku 4.5)  │
│ ○ Google (Gemini Flash)  │
└──────────────────────────┘
```

**표시 항목:**
- **현재 활성 / Active** — backend `/api/state` 의 `current_provider {provider, model}` 박제값. backend 와 매칭되는 provider 가 하이라이트.
- **변경 / Switch to** — 활성 provider 외 3개 옵션. 클릭 시 변경 가이드 모달 (ProviderGuideModal) 표시.
- **백엔드 연결 끊김 경고** — `/api/state` 응답이 없으면 노란 박스로 `백엔드 연결 끊김 — provider 변경 중이라면 재가동 후 새로고침해주세요.` 표시.

### B-5-3. Provider 변경 4단계 / 4-step provider switch

Settings 카드의 변경 옵션을 클릭하면 변경 가이드 모달이 뜹니다. **모달은 안내만 — 실제 변경은 사용자가 4단계를 직접 수행**합니다.

```
┌─────────────────────────────────────────────────────────────┐
│  Provider 변경 가이드                                    [✕]  │
│  OpenAI (gpt-4o) → Anthropic (Sonnet 4.6)                   │
│                                                              │
│  4단계로 진행합니다. 백엔드를 종료한 뒤 두 파일을 편집하고     │
│  다시 가동합니다.                                            │
│                                                              │
│  ① 백엔드 종료 / Stop backend                                │
│     backend 가동 중인 PowerShell 창에서:                     │
│         [Ctrl] + [C]                                         │
│                                                              │
│  ② .env 편집 / Edit .env                                     │
│     경로: C:\Bell_Agent\backend\writer_project\.env          │
│     아래 줄을 다음으로 변경:                                  │
│         LLM_PROVIDER=anthropic                               │
│                                                              │
│  ③ .env.anthropic 편집 / Edit overlay                        │
│     경로: C:\Bell_Agent\backend\writer_project\.env.anthropic│
│     아래 줄을 다음으로 변경 (또는 추가):                      │
│         ANTHROPIC_MODEL=claude-sonnet-4-6                    │
│     (※ ANTHROPIC_API_KEY 가 설정되어 있어야 함)               │
│                                                              │
│  ④ 재가동 / Restart                                          │
│     ┌─────────────────────────────────────────────────┐    │
│     │ cd C:\Bell_Agent\backend\writer_project          │    │
│     │ $env:PYTHONIOENCODING='utf-8'                    │    │
│     │ & C:\Bell_Agent\backend\.venv_anthropic\         │    │
│     │   Scripts\python.exe app.py --serve              │    │
│     │   --host 127.0.0.1 --port 8000                   │    │
│     └─────────────────────────────────────────────────┘    │
│                                                              │
│            [ 4단계 재가동 명령 복사 ]                         │
└─────────────────────────────────────────────────────────────┘
```

**각 단계 박제 / Step details:**

**① 백엔드 종료** — backend 가 가동 중인 PowerShell 창에서 `Ctrl+C` 입력. `Uvicorn shutdown complete.` 메시지 확인.

**② `.env` 편집** — `writer_project\.env` 파일에서 `LLM_PROVIDER` 줄을 대상 provider 로 변경:
- `LLM_PROVIDER=openai`
- `LLM_PROVIDER=anthropic`
- `LLM_PROVIDER=vertexai`
- `LLM_PROVIDER=gemini`

**③ `.env.<provider>` 편집** — provider 별 overlay 파일에서 모델명 줄을 변경:

| Provider | 파일 | 변수 |
|---|---|---|
| openai | `.env.openai` | `OPENAI_MODEL=gpt-4o` |
| anthropic (Sonnet) | `.env.anthropic` | `ANTHROPIC_MODEL=claude-sonnet-4-6` |
| anthropic (Haiku) | `.env.anthropic` | `ANTHROPIC_MODEL=claude-haiku-4-5-20251001` |
| vertexai | `.env.vertex` | `LLM_MODEL=gemini-2.5-flash` |
| gemini | `.env.gemini` | `GEMINI_MODEL=gemini-2.5-pro` |

(※ 각 파일에 해당 provider 의 API key 가 박제되어 있어야 함. 발급은 B-8 참고.)

**④ 재가동** — 해당 provider 의 가상환경으로 backend 재시작:

| Provider | 가상환경 경로 |
|---|---|
| openai | `C:\Bell_Agent\backend\.venv_openai\Scripts\python.exe` |
| anthropic (Sonnet/Haiku) | `C:\Bell_Agent\backend\.venv_anthropic\Scripts\python.exe` |
| vertexai | `C:\Bell_Agent\backend\.venv_vertex\Scripts\python.exe` |
| gemini | `C:\Bell_Agent\backend\.venv_vertex\Scripts\python.exe` (vertex 환경 재사용) |

모달 하단의 **「4단계 재가동 명령 복사」** 버튼을 클릭하면 PowerShell 명령이 클립보드에 복사됩니다.

### B-5-4. 추가 가상환경 설치 / Additional venvs

Quick Start 에서는 `.venv_openai` 만 설치했습니다. anthropic / vertexai / gemini 를 사용하려면 추가 가상환경 설치:

**Anthropic 환경 / Anthropic venv**

```powershell
cd C:\Bell_Agent\backend
python -m venv .venv_anthropic
.\.venv_anthropic\Scripts\Activate.ps1
pip install -r requirements.base.txt
pip install langchain-anthropic
deactivate
```

> ℹ️ Anthropic 은 별도 `requirements.anthropic.txt` 가 없습니다. `requirements.base.txt` + `langchain-anthropic` 만 설치. Embedding 은 OpenAI `text-embedding-3-large` 로 fallback 되므로 `.env.anthropic` 에 `OPENAI_API_KEY` 도 박제 필요.

**Vertex AI 환경 / Vertex AI venv**

```powershell
cd C:\Bell_Agent\backend
python -m venv .venv_vertex
.\.venv_vertex\Scripts\Activate.ps1
pip install -r requirements.vertex.txt
deactivate
```

Vertex AI 는 서비스 계정 JSON 인증. `.env.vertex` 에 `GOOGLE_APPLICATION_CREDENTIALS=<서비스계정-JSON-절대경로>` 박제 필요. Google Cloud Console 에서 서비스 계정 발급 + Vertex AI API 활성화 필요.

### B-5-5. 운영 정책 / Operational policy

**Provider 변경은 반드시 4단계로** — `.env` + `.env.<provider>` 파일 편집 + 재가동이 **유일한 변경 경로**입니다.

PowerShell `$env:LLM_PROVIDER=...` 같은 임시 환경변수 설정은 **무시됩니다** — backend 가동 시 `.env` 파일 값이 항상 우선 적용되도록 설계되어 있습니다. 변경 이력이 파일에 남아 추적 가능하다는 장점이 있습니다.

---

## B-6. 산출물 검증 / Output Validation

생성된 Word·PPT 를 클라이언트 제안서로 사용하기 전 빠르게 체크할 항목입니다. 각 산출물 5개씩 + 공통 cross-check + 검증 도구 박제.

### B-6-1. Word (.docx) 5가지 체크 / Word checklist

**① 제목·소제목 위계 / Heading hierarchy**
- 보고서 제목 (Heading 1) → 섹션 제목 (Heading 2) → 하위 제목 (Heading 3) 순서로 박제되었는지 확인.
- Word 의 「탐색 창」 (View → Navigation Pane) 으로 위계 한눈에 확인 가능. 건너뛴 레벨이나 잘못된 레벨 박제가 있으면 목차 자동 생성이 깨짐.

**② 각주·인용 표시 / Footnotes and citations**
- 본문의 `[1]` `[2]` 번호가 보고서 하단의 각주 정의와 1:1 매칭되는지 확인.
- 인용 출처가 도메인·파일명·발행일까지 박제되었는지. 빈 URL 이나 `(unknown)` 표시가 있으면 RAG 갱신 후 해당 섹션 재작성 권장.

**③ 표·차트·이미지 캡션 / Table and figure captions**
- 표·차트마다 `[표 1]` `[그림 1]` 형태의 캡션이 있는지 + 본문에서 캡션 번호로 참조하는지.
- xlsx 자료 (`refs/<slug>/*.xlsx`) 기반 표는 캡션 누락이 잦음. 수동 보완 필요할 수 있음.

**④ 페이지 번호·머리말·꼬리말 / Page numbers, headers, footers**
- 모든 페이지에 페이지 번호 박제되어있는지.
- 머리말에 토픽 title, 꼬리말에 회사명·작성일 박제 (사내 브랜드 가이드 따름).
- 표지·목차 페이지에서 번호 위치 어긋남 자주 발생 → Word 의 「섹션 나누기」 직접 확인 필요.

**⑤ 토픽 미션 반영도 / Mission coverage**
- `topics/<slug>.env` 에 박제한 `BLOCKAGI_OBJECTIVE_1~N` 의 모든 항목이 본문에 반영되었는지 cross-check.
- 누락된 objective 가 있으면 해당 주제로 섹션 추가 작성 또는 force_query 로 자료 보강 후 재작성.

### B-6-2. PPT (.pptx) 5가지 체크 / PPT checklist

**① 슬라이드 제목·부제 표시 / Slide titles and subtitles**
- 모든 슬라이드에 제목이 박제되어있는지. 제목 없는 슬라이드 = 제안 흐름이 끊김.
- 표지 슬라이드의 부제 (예: "광고대행사명 + 작성일 + 클라이언트명") 박제 확인.

**② 슬라이드당 글머리 기호 4~6개 / Bullet density**
- 한 슬라이드에 글머리 기호가 너무 많으면 (7개 이상) 발표 시 가독성 저하.
- 4~6개가 권장. 초과하면 슬라이드 분할 (Backend 의 자동 분할이 부족했던 경우).

**③ 인용 출처 슬라이드 하단 표시 / Source attribution**
- 데이터·인용이 있는 슬라이드는 하단에 `출처: IQVIA 2024` 또는 `Source: ...` 박제되어있는지.
- 광고기획 실무상 출처 표기 누락은 클라이언트 신뢰도에 직접 영향.

**④ 표·차트 영역 잘림 / Layout overflow**
- 표·차트가 슬라이드 영역 안에 들어왔는지 확인. PPT 자동 변환 시 한국어 텍스트 폭 계산 차이로 우측·하단 잘림 발생 가능.
- 잘림이 있으면 PowerPoint 에서 직접 크기 조정.

**⑤ 슬라이드 노트·스크립트 / Speaker notes**
- 발표용 스크립트가 노트 영역에 박제되어있는지 (PowerPoint 의 「슬라이드 노트」 보기 모드).
- 노트는 Bell Agent 가 자동 생성하지 않을 수 있음. 필요시 클라이언트 미팅 전 직접 박제.

### B-6-3. 공통 cross-check 패턴 / Word·PPT cross-check

Word 와 PPT 를 둘 다 받았다면 두 산출물 사이의 일관성도 빠르게 체크합니다.

**① 섹션 구조 일치 / Section structure**
- Word 의 Heading 2 목록 ↔ PPT 의 슬라이드 제목 목록이 동일 순서·동일 표현인지 확인.
- 한쪽에만 있는 섹션 = backend 빌드 시 sync 깨짐. `sections/<slug>/*.md` 원본 파일과 둘 다 대조.

**② 핵심 수치 일치 / Key figures**
- 시장 규모·성장률 등 핵심 수치가 Word 와 PPT 에서 동일한지.
- 다르면 RAG 자료 인용 시점의 차이일 수 있음. 원본 자료 (`refs/<slug>/*.pdf` 등) 까지 거슬러 확인.

**③ 인용 출처 동일성 / Citation consistency**
- 같은 주장을 Word·PPT 양쪽에서 인용했다면 출처도 동일해야 함.
- PPT 가 더 압축된 인용을 쓰는 경향이 있어 도메인까지만 표기하는 경우 OK, 하지만 다른 도메인을 가리키면 문제.

**④ 비주얼 자산 / Visual assets**
- Word 의 표·차트가 PPT 슬라이드에 빠짐없이 반영되었는지.
- PPT 가 시각 자료 위주이므로 누락되면 발표 메시지 약화.

### B-6-4. 검증 도구 / Validation tools

**① 원본 섹션 파일 직접 확인 / Inspect source .md files**

Word·PPT 빌드 전 단계의 원본 markdown 파일을 직접 보면 변환 손실 여부 확인 가능.

```
경로: C:\Bell_Agent\backend\writer_project\sections\<topic_slug>\
파일: <섹션슬러그>.md  (예: 시장-분석.md, 경쟁사-분석.md)
```

VS Code 또는 메모장으로 열어 본문·각주·인용 메타데이터 확인. Word 에서 깨진 표시가 원본에는 멀쩡하면 docx 변환 단계 문제, 원본에서 이미 깨졌으면 섹션 재작성 필요.

**② Backend 빌드 로그 확인 / Check build logs**

Word·PPT 다운로드 중 LogPanel 헤더를 펼치면 실시간 빌드 로그 확인 가능.

```
LogPanel 하단 → ▲ 펼치기 클릭
→ "report_builder: building section 1/7..." 같은 로그 표시
→ 빨간 ERROR 라인이 있으면 해당 섹션 빌드 실패 (재시도 또는 재작성 필요)
```

특히 PPT 빌드 중 ERROR 가 자주 발생 시점: 표 변환·차트 변환·한국어 폰트 처리. 로그 메시지 그대로 팀장 또는 개발 담당자에게 공유.

---

## B-7. 토픽 추가 / Adding a New Topic

새 클라이언트 보고서를 시작하려면 신규 토픽을 등록해야 합니다. 5단계 절차로 진행하며, 마지막에 backend 재가동이 필요합니다.

### B-7-1. 전체 절차 / Overall procedure

```
① _template 복사 → ② 토픽 .env 작성 → ③ refs/ 폴더 + 자료 배치
                                              ↓
                                      ④ backend .env 갱신
                                              ↓
                                      ⑤ backend 재가동
                                              ↓
                                      ⑥ 「최신 자료 갱신」 실행
```

### B-7-2. ① 템플릿 복사 / Copy template

`topics/_template.env.example` 을 복사해서 신규 슬러그 파일명으로 저장.

```powershell
cd C:\Bell_Agent\backend\writer_project\topics
Copy-Item _template.env.example my-new-topic.env
```

> 💡 **슬러그 명명 규칙 / Slug naming rules**
> - 영문 소문자 + 숫자 + 하이픈 (`-`) 만 사용 (예: `venfobel-vitamin`, `acme-cosmetics-2026`)
> - 한글·공백·특수문자 금지 (파일 경로 + slugify 충돌)
> - 클라이언트명-제품군-연도 패턴 권장 (예: `lg-electronics-airconditioner-2026`)

### B-7-3. ② 토픽 .env 작성 / Edit topic .env

`topics/my-new-topic.env` 를 VS Code 로 열어 박제값 작성. 최소 3개 필드 박제 필수:

```dotenv
# ── 토픽 정보 ──────────────────────────────────────
TOPIC_TITLE=ACME 화장품 2026 시장 진입 전략 보고서
TOPIC_SLUG=my-new-topic

# ── 리서치 목표 ────────────────────────────────────
BLOCKAGI_OBJECTIVE_1=한국 30대 여성 타겟 프리미엄 스킨케어 시장 규모와 카테고리 점유율 변화(2023~2026), 주요 경쟁사(아모레퍼시픽·LG생활건강·해외 럭셔리 브랜드) 포지셔닝과 가격대 분포를 파악하고, ACME 의 진입 가능 가격대·차별화 포인트를 정의한다.
BLOCKAGI_OBJECTIVE_2=주요 광고 채널(Instagram·올리브영·홈쇼핑·인플루언서) 별 30대 여성 도달률과 광고 단가, 경쟁사의 캠페인 사례 분석으로 효율적 미디어 믹스와 메시지 톤을 설계한다.
BLOCKAGI_OBJECTIVE_3=화장품법·표시광고법·기능성 화장품 인증 등 규제 환경과 클레임 허용 범위를 정리하고, ACME 제품 라인의 효능 표현 가능 영역을 명확히 한다.
```

**박제 필수 항목 / Required fields**

| 변수 | 용도 | 형식 |
|---|---|---|
| `TOPIC_TITLE` | Header 표시 + 보고서 제목 | 한글 자유 서술 |
| `TOPIC_SLUG` | 파일·폴더 식별자 | 파일명과 동일 (영문 소문자) |
| `BLOCKAGI_OBJECTIVE_1` ~ `_N` | 리서치 목표 (최대 10개) | 짧은 키워드 또는 서술형 장문 |

> 💡 **objective 작성 팁** — 서술형 장문일수록 LLM 이 더 구체적인 보고서를 산출합니다. 단순 키워드보다 "무엇을 + 어떤 데이터로 + 왜 분석하는지" 까지 박제하는 게 결과 품질에 직결.

### B-7-4. ③ refs/ 폴더 + 자료 배치 / Set up refs folder

토픽 슬러그와 동일한 이름의 폴더를 `refs/` 아래에 생성하고 클라이언트 자료 배치.

```powershell
mkdir C:\Bell_Agent\backend\writer_project\refs\my-new-topic
```

Windows 탐색기에서 해당 폴더로 이동 후 자료 복사·붙여넣기.

```
refs\my-new-topic\
├─ 시장조사_2025.pdf
├─ 경쟁사_분석.docx
├─ 매출데이터_2024.xlsx
├─ 브랜드_가이드.pptx
└─ 클라이언트_요청사항.md
```

**지원 파일 형식 / Supported formats** — `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.md` (`LOCAL_RAG_GLOBS` 박제값 적용)

> 💡 폴더 안에 하위 폴더를 만들어도 OK (예: `refs/my-new-topic/시장조사/`). `LOCAL_RAG_GLOBS` 가 재귀적 (`refs/**/*.pdf`) 검색.

### B-7-5. ④ backend `.env` 갱신 / Update backend `.env`

`writer_project\.env` 의 `TOPIC_SLUG` 줄을 신규 슬러그로 변경.

```dotenv
# 변경 전
TOPIC_SLUG=venfobel-vitamin

# 변경 후
TOPIC_SLUG=my-new-topic
```

다른 필드 (`LLM_PROVIDER`, `LLM_MODEL`, `PROJECT_ROOT`) 는 그대로 유지.

### B-7-6. ⑤ backend 재가동 / Restart backend

가동 중인 backend 의 PowerShell 창에서 `Ctrl+C` 종료 후 재가동.

```powershell
cd C:\Bell_Agent\backend
.\.venv_openai\Scripts\Activate.ps1
cd writer_project
$env:PYTHONIOENCODING="utf-8"
python app.py --serve --host 127.0.0.1 --port 8000
```

재가동 후 브라우저 새로고침 (`F5`). Header 에 신규 토픽 title 이 표시되면 성공.

### B-7-7. ⑥ RAG 인덱스 구축 / Build RAG index

frontend Sidebar 「자료」 카드의 **「최신 자료 갱신」** 버튼 클릭. `refs/my-new-topic/` 의 모든 파일 + Naver/Tavily 웹 검색 결과가 ChromaDB 에 임베딩됩니다 (30초~3분 소요).

완료되면 Sidebar 「자료」 카드에 `N개 파일 학습됨` 표시. 이후 (B-2) 워크플로우 따라 목차 생성 → 섹션 작성 진행.

### B-7-8. (선택) topic_config.json 박제 / Optional topic config

도메인별 가중치·xlsx 키워드 가중치 등 토픽별 RAG 튜닝이 필요한 경우 `topics/<slug>.config.json` 박제.

```powershell
cd C:\Bell_Agent\backend\writer_project\topics
Copy-Item _example.config.json my-new-topic.config.json
```

VS Code 로 열어 박제값 수정. 주요 필드:

- **`domain_bonus`** — 신뢰 도메인은 `+1.0` 가중치, 노이즈 도메인은 `-0.5` 페널티
- **`xlsx_keywords`** — 매출·카테고리·금액 등 핵심 키워드의 검색 가중치

```json
{
  "domain_bonus": {
    "groups": [
      {
        "name": "trusted_industry_media",
        "score": 1.0,
        "hosts": ["cosmeticsnews.co.kr", "beautyhank.com"]
      },
      {
        "name": "penalties",
        "score": -0.5,
        "hosts": ["unreliable-blog.example.com"]
      }
    ]
  }
}
```

> 💡 `topic_config.json` 박제는 RAG 품질이 충분치 않을 때만 진행. 기본값으로도 일반적인 토픽은 잘 동작합니다. 자세한 필드는 `topics/_example.config.json` 의 주석 참고.

### B-7-9. 토픽 전환 / Switching topics

이미 박제한 여러 토픽 간 전환은 더 간단합니다.

```
1. backend .env 의 TOPIC_SLUG 만 변경
2. backend 재가동 (Ctrl+C → python app.py --serve ...)
3. 브라우저 새로고침
```

> 💡 ChromaDB 인덱스는 `chroma/<topic_slug>/` 폴더에 토픽별로 분리 저장되어 있어서 토픽 전환 시 재인덱싱 불필요. 같은 토픽에 자료를 추가했을 때만 「최신 자료 갱신」 재실행.

---

## B-8. API key 직접 발급 / Issue Your Own API Keys

테스트 기간에는 팀장이 발급한 공용 API key 를 사용해도 됩니다. 본인 발급분으로 사용하려면 아래 안내를 참고하세요.

### B-8-1. 보안 안내 / Security guidelines

> 🔒 **API key 는 비밀번호와 동일하게 취급하세요.**
>
> - **공유 금지** — 메신저·이메일·Git commit·스크린샷에 절대 노출 금지
> - **gitignore 확인** — `.env`, `.env.<provider>` 파일이 Git 에 포함되지 않도록 확인 (Bell Agent backend 는 기본 박제됨)
> - **분실·노출 시 즉시 revoke** — 각 콘솔의 API keys 페이지에서 해당 키 삭제 후 신규 발급
> - **사용량 모니터링** — 각 콘솔의 Usage 탭에서 비정상 사용 패턴 주기적 확인

### B-8-2. OpenAI (gpt-4o, embedding)

- **콘솔 / Console** — [platform.openai.com](https://platform.openai.com) 로그인 (Google·Microsoft·이메일 가입 가능)
- **발급 / Issue** — 좌측 메뉴 `API keys` → 우상단 `Create new secret key` → 이름 지정 → 키 복사 (한 번만 표시됨)
- **박제 / Save** — `writer_project\.env.openai` 의 `OPENAI_API_KEY=sk-...` 줄에 박제
- **결제 등록** — 좌측 메뉴 `Billing` → 카드 등록 + 초기 크레딧 충전 ($5~10 권장)
- **테스트** — backend 재가동 후 「최신 자료 갱신」 클릭 → 정상 임베딩 시 발급 성공

### B-8-3. Anthropic (Claude Sonnet/Haiku)

- **콘솔 / Console** — [console.anthropic.com](https://console.anthropic.com) 로그인 (Google·이메일 가입 가능)
- **발급 / Issue** — 좌측 메뉴 `API Keys` → `Create Key` → 이름 지정 → 키 복사 (한 번만 표시됨)
- **박제 / Save** — `writer_project\.env.anthropic` 의 `ANTHROPIC_API_KEY=sk-ant-...` 줄에 박제
- **결제 등록** — 좌측 메뉴 `Plans & Billing` → 카드 등록 + 크레딧 충전 ($5~10 권장)
- **OpenAI key 도 박제 필요** — Anthropic 은 embedding 을 OpenAI `text-embedding-3-large` 로 fallback 하므로 `.env.anthropic` 에 `OPENAI_API_KEY` 도 함께 박제 (B-5-4 참고)

### B-8-4. Google AI Studio (Gemini 2.5 Pro)

- **콘솔 / Console** — [aistudio.google.com](https://aistudio.google.com) Google 계정 로그인
- **발급 / Issue** — 좌상단 `Get API key` → `Create API key` → 프로젝트 선택 또는 신규 생성 → 키 복사
- **박제 / Save** — `writer_project\.env.gemini` 의 `GEMINI_API_KEY=...` 줄에 박제
- **무료 한도** — 일정 RPM·일일 토큰 한도 내 무료 사용 가능. 한도 초과 시 결제 등록 필요
- **참고** — Gemini 는 frontend Settings 카드에 노출되지 않으므로 `.env` 직접 편집으로만 사용 가능 (B-5-1 참고)

### B-8-5. Vertex AI (Gemini 2.5 Flash)

Vertex AI 는 API key 가 아닌 **서비스 계정 JSON 인증** 방식이라 발급 절차가 복잡합니다.

> 📌 **회사에 요청 / Request from team** — 사내 Google Cloud 프로젝트 권한 + 서비스 계정 JSON 파일이 필요합니다. 개인 발급보다는 팀장·인프라 담당자에게 요청하는 것을 권장합니다.

받은 JSON 파일을 본인 PC 의 안전한 경로 (예: `C:\Bell_Agent\backend\writer_project\local\vertex-sa.json`) 에 저장 후 `.env.vertex` 에 박제:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=C:\Bell_Agent\backend\writer_project\local\vertex-sa.json
GCP_PROJECT_ID=<프로젝트-ID>
GCP_REGION=us-central1
```

### B-8-6. Naver / Tavily (웹 검색)

RAG 갱신 시 웹 검색에 사용. 두 가지 옵션:

- **회사 제공 key 사용 / Use company key** — 팀장이 발급한 공용 key 를 `.env` 에 박제 (테스터 기본 옵션)
- **개인별 별도 발급 / Issue your own**
  - **Naver** — [developers.naver.com](https://developers.naver.com) → 애플리케이션 등록 → 검색 API 권한 → Client ID·Secret 발급
  - **Tavily** — [tavily.com](https://tavily.com) 로그인 → Dashboard → API Keys → 키 발급

박제 위치 — `writer_project\.env` 또는 `.env.openai` 등 활성 overlay 파일에:

```dotenv
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
TAVILY_API_KEY=tvly-...
```

> 💡 웹 검색 key 가 박제되어 있지 않거나 무효하면 「최신 자료 갱신」 시 local RAG (`refs/` 폴더 자료) 만 임베딩되고 웹 검색은 skip 됩니다. LogPanel 에 경고 표시.

---

# (C) FAQ + 트러블슈팅 / FAQ + Troubleshooting

운영 중 자주 마주치는 질문과 증상별 해결 가이드. 문제가 해결되지 않으면 LogPanel 의 에러 메시지를 캡처해서 팀장 또는 개발 담당자에게 공유해 주세요.

## C-1. 자주 묻는 질문 / FAQ

### Q1. 보고서 1개 만드는 데 얼마나 걸리나요?

토픽 자료량과 섹션 수에 따라 다르지만 평균 30~60분 소요됩니다 (자료 갱신 30초~3분 + 목차 1~2분 + 섹션 7개 × 2~5분 + 다운로드 30초). gpt-4o 기준이며, Anthropic Sonnet 4.6 사용 시 약 2배 더 걸립니다.

### Q2. 토픽 자료를 추가하면 기존 보고서가 자동으로 갱신되나요?

아니요. 새 자료를 `refs/<slug>/` 폴더에 추가한 후 「최신 자료 갱신」 을 실행해야 ChromaDB 인덱스가 갱신됩니다. 이미 작성된 섹션은 영향 없고, 갱신 이후 **새로 작성하거나 재작성**하는 섹션부터 새 자료가 반영됩니다.

### Q3. 같은 토픽으로 동료와 동시에 작업할 수 있나요?

각자 PC 에 독립 설치되어 있으므로 데이터 충돌 없이 동시 작업 가능하지만, 결과물은 **각자 PC 에만 저장**됩니다. 작성된 섹션을 공유하려면 Word/PPT 다운로드 후 사내 공유 폴더에 업로드하거나, `sections/<slug>/*.md` 원본 파일을 메신저·메일로 직접 전달해야 합니다.

### Q4. 산출물을 클라이언트에게 바로 보내도 되나요?

**아니요.** Bell Agent 산출물은 **클라이언트 제안용 초안**입니다. 외부 공유 전 반드시 다음 항목을 검토하세요 — (1) 팀장·본부장 내용 검토, (2) 산출물 검증 체크리스트 (B-6 참고) 통과, (3) 출처 정확성·표현 적절성 확인. 보안 박스 (가이드 최상단) 의 자산 보호 정책도 함께 준수.

### Q5. backend 가 응답하지 않는 것 같아요. 어떻게 확인하나요?

LogPanel 헤더의 `▲ 펼치기` 클릭 후 최근 로그 시각 확인. 마지막 로그가 1분 이상 정지되어 있고 새 로그가 안 올라오면 LLM 호출 타임아웃 또는 web 검색 정지 가능성. LogPanel 의 ⛔ 취소 버튼 클릭 → 재시도. 그래도 안 되면 PowerShell backend 창에서 에러 메시지 확인 후 backend 재가동.

### Q6. ChatGPT 와 무엇이 다른가요?

세 가지 핵심 차이가 있습니다 — (1) **RAG 기반 인용** — 클라이언트 자료 (`refs/`) 와 웹 검색 결과를 인용해서 출처가 명확함 (ChatGPT 의 일반 지식 기반과 다름), (2) **자동 docx/pptx 변환** — Word·PPT 산출물이 한 번에 생성됨, (3) **토픽 미션 박제** — `BLOCKAGI_OBJECTIVE_*` 로 보고서 방향을 사전 박제하므로 일관성 있는 결과.

---

## C-2. 증상별 해결 / Symptom-based Troubleshooting

### S1. 「최신 자료 갱신」 등 버튼이 비활성화되어 클릭 안 됨

**원인** — backend 와 frontend 의 연결이 끊겼거나, `/api/state` 응답이 없는 상태.

**해결**
1. backend PowerShell 창이 정상 가동 중인지 확인 (`Uvicorn running on http://127.0.0.1:8000` 메시지 표시)
2. backend 가 멈춰있으면 재가동 (`python app.py --serve --host 127.0.0.1 --port 8000`)
3. 브라우저 새로고침 (`F5`) → Sidebar 「설정」 카드의 노란 경고 박스가 사라지면 정상 복구

### S2. PPT 다운로드 실패 / 빈 파일 / 에러 알림

**원인** — `report_builder.py` 의 pptx 변환 중 표·차트·한국어 폰트 처리 단계에서 예외 발생.

**해결**
1. LogPanel 을 펼쳐 빌드 로그 확인 — `report_builder: building section N/M ...` 부분에서 ERROR 라인 검색
2. 특정 섹션이 원인이면 해당 섹션 재작성 (`write: <섹션제목>`) 후 PPT 재다운로드
3. 그래도 안 되면 LogPanel 의 빨간 ERROR 라인 캡처해서 팀장·개발 담당자에게 공유

### S3. Word/PPT 또는 콘솔 출력에서 한글 깨짐

**원인** — PowerShell 의 기본 codec 이 cp949 (한국어 Windows) 이라 UTF-8 출력이 깨짐. 또는 docx/pptx 의 한국어 폰트 매핑 누락.

**해결**
1. backend 가동 명령 앞에 `$env:PYTHONIOENCODING="utf-8"` 박제 확인 (Quick Start A-3 참고)
2. PowerShell 의 codec 변경: `chcp 65001` 실행 후 backend 재가동
3. docx 내부 한글 깨짐 (□ 표시) — Word 에서 직접 폰트를 「맑은 고딕」 으로 일괄 변경

### S4. LogPanel 로그가 멈춤 (1분 이상 새 로그 없음)

**원인** — LLM API 호출 타임아웃 또는 web 검색 응답 지연. 외부 네트워크 문제도 가능.

**해결**
1. LogPanel ⛔ 취소 클릭 → 진행 중 작업 중단
2. 인터넷 연결 확인 (`ping platform.openai.com` 또는 콘솔 사이트 직접 접속)
3. provider API key 의 사용량 한도 또는 결제 상태 확인 (각 콘솔의 Usage·Billing)
4. 다시 명령 재시도. 반복 발생 시 다른 provider 로 전환 후 시도 (B-5 참고)

### S5. backend 가 시작 안 됨

**원인** — port 8000 충돌, `.env` 누락·오타, 가상환경 활성화 누락, 또는 API key 누락.

**해결**
1. **port 충돌** — PowerShell 에서 `netstat -ano | findstr :8000` → 다른 프로세스가 사용 중이면 종료 또는 다른 port 로 가동 (`--port 8001`)
2. **`.env` 누락** — `writer_project\.env` 파일 존재 확인 (`LLM_PROVIDER`, `TOPIC_SLUG`, `PROJECT_ROOT` 박제 필수)
3. **venv 누락** — `.\.venv_openai\Scripts\Activate.ps1` 명령으로 활성화했는지 확인 (프롬프트에 `(.venv_openai)` 표시되어야 함)
4. **API key 누락** — 해당 provider 의 `.env.<provider>` 파일에 API key 박제 확인

### S6. frontend 가 시작 안 됨 / 접속 안 됨

**원인** — `npm install` 미실행, port 3000 충돌, 또는 `.env.local` 누락.

**해결**
1. **`npm install` 재실행** — `C:\Bell_Agent\frontend` 에서 `npm install` 실행
2. **port 3000 충돌** — `netstat -ano | findstr :3000` 확인. 충돌 시 `npm run dev -- -p 3001` 로 다른 port 가동
3. **`.env.local` 누락** — `frontend\.env.local` 파일 존재 확인 (`NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` 박제 필수)

### S7. provider 를 변경했는데 적용되지 않음

**원인** — 4단계 중 ① backend 종료 누락이 가장 흔함. PowerShell `$env:` 임시 설정은 무효 (B-5-5 참고).

**해결**
1. backend PowerShell 창에서 `Ctrl+C` 입력 → `Uvicorn shutdown complete.` 메시지 확인
2. `.env` 와 `.env.<provider>` 두 파일 모두 편집했는지 재확인 (한 쪽만 변경 시 무효)
3. 해당 provider 의 가상환경으로 재가동 (예: anthropic 이면 `.venv_anthropic` 사용)
4. 브라우저 새로고침 → Sidebar 「설정」 카드의 현재 활성 표시 확인

### S8. 섹션 작성 결과가 너무 짧거나 자료 인용이 적음

**원인** — RAG 자료 부족, objective 가 너무 추상적, 또는 토픽과 섹션 제목의 매칭 약함.

**해결**
1. **RAG 자료 보강** — `refs/<slug>/` 폴더에 관련 자료 추가 후 「최신 자료 갱신」 재실행
2. **force_query 로 키워드 강제 검색** — `force_query: <구체적 키워드>` 입력 후 섹션 재작성 (B-4-1 참고)
3. **objective 구체화** — `topics/<slug>.env` 의 `BLOCKAGI_OBJECTIVE_*` 를 서술형 장문으로 보강 (B-2-3 박제 팁 참고) 후 backend 재가동
4. 그래도 부족하면 더 상세한 결과를 만드는 provider 로 전환 (Anthropic Sonnet 4.6 권장)

---

## C-3. 박제 자산 / Reference Assets

본 가이드 외 추가 참조 자산:

- **개발자용 상세 문서** — `writer_project\README-dev.md`, `writer_project\README-dev-2.md`
  - LangGraph 노드 상세 구성, 라우터 로직, 측정·평가 트랙 박제 자산
- **Backend repo** — [github.com/Sungsu1203/bell-agent-backend](https://github.com/Sungsu1203/bell-agent-backend) (운영 branch: `main`)
- **Frontend repo** — [github.com/Sungsu1203/bell-agent-frontend](https://github.com/Sungsu1203/bell-agent-frontend) (운영 branch: `master`)

---

*— 끝 / End —*

이 가이드는 Bell Agent 운영 초기 버전입니다. 누락된 내용이나 개선 제안은 팀장에게 전달해 주세요.
