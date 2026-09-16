# Doc Fact Checker — 문서 검증 웹앱

`doc-fact-checker` 스킬을 그대로 실행 엔진으로 쓰는 웹앱입니다. 문서를 올리면 Claude API의 코드 실행 컨테이너 안에서 스킬 절차(주장 인벤토리 → 계층별 검증 → 판정 → 보고서)가 돌아가고, 결과를 구조화된 JSON으로 받아 화면에 보여줍니다.

```
브라우저 (Next.js, Vercel)
   │  로그인 · 파일 업로드 · 상태 폴링 · 결과 표시 · 조직 관리
   ▼
백엔드 (FastAPI, Python)  ──► Claude API
   │  인증 · 작업 큐 · 후처리 · PDF     ├─ 커스텀 스킬: doc-fact-checker (컨테이너 /skills/ 에 탑재)
   │                                   ├─ code_execution  : Python 재계산, 텍스트 추출
   │                                   ├─ web_search      : 외부 사실 확인
   │                                   ├─ web_fetch       : 출처 원문 대조
   │                                   └─ law_search / law_article : 국가법령정보센터 오픈API (백엔드가 실행하는 클라이언트 도구)
   ▼
data/  dfc.sqlite3 (조직·사용자·세션·초대·작업)
       orgs/<org_id>/jobs/<id>/uploads/, outputs/(result.json, report.md, report.pdf, corrected.md, log.json)
```

검증 로직은 `skill/doc-fact-checker/`에만 있습니다. 앱 코드는 실행·복구·기록·표시·인증만 맡습니다.

## 폴더

| 경로 | 내용 |
|---|---|
| `skill/doc-fact-checker/` | API 업로드용 스킬. 원본 스킬 + `scripts/extract_text.py`(PDF/DOCX/HWPX 변환) + `references/result-schema.md`(앱이 읽는 JSON 스키마) + 컨테이너 환경 지침 |
| `backend/` | FastAPI. `verifier.py` Claude 호출(서버 도구 + 법령 클라이언트 도구 루프), `postprocess.py` 판정 규칙 강제, `lawapi.py` 법령 오픈API, `report_pdf.py` PDF, `auth.py`/`db.py` 인증·조직(SQLite) |
| `frontend/` | Next.js 15 (App Router). 로그인/초대 가입 → 업로드 → 진행 로그 → 등급·지적 항목·검산표·권장 조치·실행 기록 → PDF/MD/JSON 다운로드. `/org`에서 구성원·초대·사용량 |

## 처음 실행하기

### 1. 스킬 업로드 (한 번만)

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/upload_skill.py          # → skill_01... 출력
```

### 2. 백엔드

```bash
cp .env.example .env                    # DFC_SKILL_ID, CORS_ORIGINS, (선택) LAW_API_OC 채우기
playwright install chromium             # PDF 보고서용 (Docker 이미지는 자동 설치)
python scripts/create_org.py --org "TEN AI" --email admin@tenai.kr --password '********' --name 홍길동
uvicorn app.main:app --reload --port 8000
```

`create_org.py`가 첫 조직과 관리자(owner) 계정을 만듭니다. 팀원은 관리자가 앱의 조직 화면에서 만든 초대 코드로 가입합니다.
API 키 없이 화면만 먼저 보려면 `.env`에 `MOCK_VERIFIER=1`을 두면 샘플 결과가 나옵니다.

**법령 오픈API**: [open.law.go.kr](https://open.law.go.kr)에서 OPEN API를 신청하면 이메일 아이디가 인증값(OC)입니다. `.env`의 `LAW_API_OC`에 넣으면 검증 중 `law_search`·`law_article` 도구가 활성화되어 조문 단위 원문·시행일자를 기관 원자료에서 직접 받습니다. 비워 두면 웹 검색으로 대체합니다.

### 3. 프론트

```bash
cd frontend
cp .env.example .env.local              # NEXT_PUBLIC_API_BASE=http://localhost:8000
npm install && npm run dev              # http://localhost:3000
```

### 4. 테스트

```bash
cd backend && python -m pytest tests            # 후처리 규칙 · 인증/조직 격리 · 법령 API 파서
python ../skill/doc-fact-checker/scripts/extract_text.py 문서.hwpx --out /tmp/doc.md   # 변환 확인
```

## 배포

- **프론트 → Netlify**: 저장소를 연결하면 루트의 `netlify.toml`(base=`frontend`, Next.js 런타임)이 적용됩니다. 사이트 설정 → Environment variables에 `NEXT_PUBLIC_API_BASE`(백엔드 주소)를 넣고 다시 배포하세요. 이 값은 빌드 시점에 번들에 박히므로 바꾸면 재배포가 필요합니다.
- **프론트 → Vercel**: 저장소 연결 후 Root Directory를 `frontend`로, 환경변수 `NEXT_PUBLIC_API_BASE`에 백엔드 주소.
- **백엔드 → 컨테이너 호스팅** (Cloud Run, Railway, Fly 등): `backend/Dockerfile` 사용. `/data` 볼륨을 붙여 작업 기록을 보존. 검증 한 건이 수 분 걸리므로 요청 타임아웃과 인스턴스 최소 수(0으로 내려가지 않게)를 조정.
- 백엔드 `.env`의 `CORS_ORIGINS`에 Netlify/Vercel 도메인 추가. 반드시 HTTPS로 서비스합니다(세션 토큰이 헤더로 오갑니다).
- 고객 셀프 온보딩을 열려면 `ALLOW_SELF_SIGNUP=1` (로그인 화면에 '새 조직 만들기'가 생김). 내부용은 0으로 두고 초대 코드만 사용.
- 운영에서는 `DFC_SKILL_VERSION`을 `latest` 대신 `skver_...`로 고정. 스킬을 고친 뒤 `python scripts/upload_skill.py --skill-id skill_...`로 새 버전을 만들고, 검토 후 버전을 올립니다.

## 앱이 코드로 강제하는 것 (스킬의 검증자 원칙)

| 규칙 | 구현 |
|---|---|
| 근거 없는 '오류 확인' 금지 | `evidence.type`이 none이거나 `detail`이 비면 '의심'으로 강등 + `downgraded_no_evidence` 플래그 표시 |
| 판정 건수·등급은 자기보고를 믿지 않음 | `findings`에서 재계산. 모델 등급과 다르면 화면에 그 사실을 표시 (D만 모델 판단 유지) |
| 확인됨·검증 불가에는 심각도 없음 | 강제 null |
| 검증 불가 30% 초과 시 경고 | `needs_evidence_flag` → '근거 보강 필요' 표시 |
| 검색·fetch 예산 | `WEB_SEARCH_MAX_USES`, `WEB_FETCH_MAX_USES` (도구 `max_uses`) |

## 비용·시간 감각

- 문서 한 건: 수 분(pause_turn으로 여러 라운드 이어감), 토큰은 문서 길이 + 검색 결과에 비례.
- 서버 도구 웹 검색·fetch가 요청에 포함되면 코드 실행 요금은 별도로 붙지 않습니다(토큰 비용만). 웹 검색 자체는 회당 과금.
- 정확도가 중요하면 `CLAUDE_MODEL=claude-opus-5`, 비용을 줄이려면 `claude-sonnet-5`.

## 인증·조직 모델

- 사용자는 정확히 한 조직에 속합니다. 역할은 관리자(owner)·구성원(member).
- 검증 기록·파일은 조직 단위로 격리됩니다: DB 조회는 항상 `org_id`로 걸고, 파일 경로에도 `org_id`가 들어갑니다. 다른 조직의 작업 ID를 알아도 404입니다.
- 세션은 Bearer 토큰(30일). DB에는 토큰의 SHA-256 해시만 저장. 비밀번호는 scrypt.
- 로그인 5회 실패 시 5분 잠금(프로세스 메모리 기준).
- 조직별 월 검증 한도(`monthly_job_limit`, 기본 100)를 넘으면 새 작업을 만들 수 없습니다. 한도 변경은 SQLite `orgs` 테이블을 직접 수정하거나 운영 스크립트를 추가하세요.
- 구성원 비활성화 시 세션이 즉시 무효화됩니다.

## 알려진 한계 · 다음 단계

1. **스캔 PDF**: 텍스트 추출이 실패하면 검증을 중단하고 표시합니다. OCR 단계는 아직 없습니다.
2. **HWPX**: 본문·표는 읽지만 각주·머리말·그림 안 텍스트는 건너뜁니다.
3. **법령 API**: 현행 법령(law)·조항호목(lawjosub)만 씁니다. 행정규칙·자치법규(admrul/ordin), 시행일 기준 조회(eflaw)는 같은 방식으로 도구를 추가하면 됩니다. 인증값 트래픽 한도는 open.law.go.kr 계정 정책에 따릅니다.
4. **저장소**: SQLite 단일 파일. 다중 인스턴스·대용량이면 `db.py`의 연결만 PostgreSQL로 바꾸면 됩니다(SQL은 표준 범위).
5. **인증 고도화**: 비밀번호 재설정 메일, 2단계 인증, SSO는 없습니다. 고객 제공 단계에서 이메일 발송 경로가 생기면 추가하세요.
6. **PDF 폰트**: Chromium이 CDN에서 Pretendard를 받습니다. 외부망이 막힌 서버라면 폰트 파일을 이미지에 넣고 `report_pdf.py`의 `@import`를 로컬 `@font-face`로 바꾸세요.
