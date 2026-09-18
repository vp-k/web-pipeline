# Worked Example: 가입 폼 이메일 형식 검증 (T2, frontend + api)

전제: [config-cookbook.md](config-cookbook.md) (g) 구성의 모노레포(`frontend/`, `backend/`, `contracts/`), `approval_policy: standard`, `verification.scopes` 설정됨(component `web`, `api`). 변경 파일은 `frontend/src/features/signup/SignupForm.tsx`, `frontend/src/features/signup/email.ts`, `backend/src/routes/signup.ts`, `contracts/signup.schema.json`. 이 경로들은 보호 rule 에 걸리지 않는다. 같은 코드가 `.../auth/...` 아래에 있으면 `*auth*` rule 로 T3 `authentication` 이 되어 이 예시의 절차(로컬 리뷰)로는 끝나지 않는다.

Tier 근거: `api` 도메인 floor 가 T2. T2 이므로 `PLAN.md` 가 추가로 필요하고 리뷰는 로컬 self-review 다.

## 1. 생성

```console
python -m web_pipeline new --task SIGNUP-014 --title "Signup email format validation" --tier T2 --domains frontend,backend,api --base-ref HEAD
```

`--base-ref HEAD` 는 생성 시점의 commit 으로 고정된다. 이후 `Docs/Work/SIGNUP-014/` 의 파일을 채운다. `STATE.md` 는 건드리지 않는다.

## 2. BRIEF.md

```markdown
# Brief

## Objective
가입 폼과 POST /api/signup 이 이메일 형식을 같은 규칙으로 검증한다.

## In scope
- 웹: 제출 전 형식 검사, 인라인 오류 표시.
- API: 형식 오류 요청을 422 로 거부하고 사용자를 만들지 않는다.
- 계약: contracts/signup.schema.json 에 422 오류 응답을 추가한다.

## Out of scope
이메일 실재 여부 확인(MX, 인증 메일), 중복 이메일 처리 변경, 다른 필드 검증.

## Acceptance criteria
- AC-01: 형식이 틀린 이메일은 제출되지 않고 필드 아래에 오류가 보인다.
- AC-02: API 는 형식 오류에 422 와 필드 오류 본문을 돌려주고 사용자를 만들지 않는다.
- AC-03: 웹은 API 의 422 응답을 같은 필드 오류로 표시한다.

## Constraints and confirmed decisions
- 규칙: 공백 없음, @ 하나, 도메인에 점 하나 이상, 전체 254자 이하. 앞뒤 공백은 제거 후 검사한다.
- 형식 오류 응답은 422 와 errors 배열이다 (Q-01, 사용자 답변).
- 현재 관찰: backend/src/routes/signup.ts 는 이메일을 검사하지 않고 그대로 저장한다 (base_ref 기준).

## Normal and exceptional scenarios
정상 입력, 빈 값, 형식 오류, 255자 이상, 앞뒤 공백, 클라이언트 검사를 우회한 직접 API 호출.

## Open planning questions
Q-01 (해결됨).
```

`DOR.md` 는 템플릿 체크리스트를 실제 상태로 채우고, `PLAN.md`(T2+)는 다음처럼 짧아도 된다. 어떤 `.md` 에도 `TBD`/`TODO`/`UNSET` 만 있는 줄이 남으면 안 된다.

```markdown
# Plan

## Objective and exclusions
BRIEF 와 같다. 실재 여부 확인과 중복 처리는 제외.

## Affected boundaries and contracts
component web(browser), api(server). 계약 http-api 의 contracts/signup.schema.json 에 422 응답 추가(기존 응답은 그대로, 하위 호환).

## Milestones
1. 계약에 422 오류 응답 추가. 2. API 검증 + provider/integration 테스트. 3. 웹 검증 + unit/consumer/e2e 테스트.

## Acceptance-to-verification map
AC-01: web-unit, browser-e2e. AC-02: contract-provider, integration. AC-03: contract-consumer, browser-e2e.

## Compatibility, migration, and rollback
DB 변경 없음. 롤백은 commit revert.

## Decisions and approvals
보호 변경 없음. standard 정책의 로컬 self-review.
```

## 3. ACCEPTANCE.json

`checks` 는 설정에 enabled 이고 `Full` 또는 `Policy` 프로필을 가진 command id 여야 한다.

```json
{
  "criteria": [
    {"id": "AC-01", "description": "형식이 틀린 이메일은 제출되지 않고 필드 아래에 오류가 보인다.", "checks": ["web-unit", "browser-e2e"]},
    {"id": "AC-02", "description": "POST /api/signup 은 형식 오류에 422 와 errors 배열을 돌려주고 사용자를 만들지 않는다.", "checks": ["contract-provider", "integration"]},
    {"id": "AC-03", "description": "웹은 API 의 422 응답을 이메일 필드 오류로 표시한다.", "checks": ["contract-consumer", "browser-e2e"]}
  ]
}
```

## 4. SCOPE.json

`verification.scopes` 가 설정된 프로젝트에서만 둔다(없는 프로젝트에 두면 오류). 생략하면 변경 경로에서 component 를 추론한다. `level: "task"` 는 `members` 가 비어 있어야 한다.

```json
{"level": "task", "components": ["web", "api"], "members": []}
```

## 5. CLARIFICATIONS.json

`new` 가 만든 템플릿의 `task_id`/`revision` 을 유지하고 6개 영역을 모두 채운다. `document` source 의 `excerpt` 는 그 파일에 **글자 그대로** 있어야 하고, 파일 바이트는 fingerprint 에 묶인다. 질문은 먼저 `"resolution": null` 로 기록해 사용자에게 묻고, 실제 답을 받은 뒤에만 채운다. 에이전트의 추천안은 답이 아니다.

```json
{
  "schema_version": "1.0",
  "task_id": "SIGNUP-014",
  "revision": 1,
  "analysis": [
    {"area": "goal_scope", "finding": "가입 폼과 가입 API 의 이메일 형식 검증만 다룬다. 실재 확인과 중복 처리는 제외.",
     "sources": [{"kind": "user_message", "reference": "local session: SIGNUP-014 요청", "excerpt": "가입 폼에 이메일 형식 검증을 추가해 줘"},
                 {"kind": "document", "reference": "Docs/Work/SIGNUP-014/BRIEF.md", "excerpt": "이메일 실재 여부 확인(MX, 인증 메일), 중복 이메일 처리 변경, 다른 필드 검증."}]},
    {"area": "user_flow", "finding": "입력 후 제출 시 형식 오류면 제출을 막고 필드 아래에 오류를 보인다. 고치면 정상 제출된다.",
     "sources": [{"kind": "document", "reference": "Docs/Work/SIGNUP-014/BRIEF.md", "excerpt": "- 웹: 제출 전 형식 검사, 인라인 오류 표시."}]},
    {"area": "exceptions", "finding": "빈 값, 255자 이상, 앞뒤 공백, 클라이언트 검사를 우회한 직접 호출을 포함한다.",
     "sources": [{"kind": "document", "reference": "Docs/Work/SIGNUP-014/BRIEF.md", "excerpt": "정상 입력, 빈 값, 형식 오류, 255자 이상, 앞뒤 공백, 클라이언트 검사를 우회한 직접 API 호출."}]},
    {"area": "data_integrations", "finding": "DB 스키마 변경 없음. 계약 파일에 422 응답이 추가되며 기존 응답과 하위 호환이다. 외부 서비스 호출 없음.",
     "sources": [{"kind": "document", "reference": "Docs/Work/SIGNUP-014/BRIEF.md", "excerpt": "- 계약: contracts/signup.schema.json 에 422 오류 응답을 추가한다."}]},
    {"area": "constraints", "finding": "웹과 API 가 같은 규칙을 쓴다. 서버 검증이 기준이며 클라이언트 검증만으로 끝내지 않는다.",
     "sources": [{"kind": "document", "reference": "Docs/Work/SIGNUP-014/BRIEF.md", "excerpt": "- 규칙: 공백 없음, @ 하나, 도메인에 점 하나 이상, 전체 254자 이하. 앞뒤 공백은 제거 후 검사한다."}]},
    {"area": "acceptance", "finding": "AC-01 은 웹 단위+E2E, AC-02 는 provider 계약+실제 DB 통합, AC-03 은 consumer 계약+E2E 로 검증한다.",
     "sources": [{"kind": "document", "reference": "Docs/Work/SIGNUP-014/BRIEF.md", "excerpt": "- AC-02: API 는 형식 오류에 422 와 필드 오류 본문을 돌려주고 사용자를 만들지 않는다."}]}
  ],
  "questions": [
    {"id": "Q-01",
     "question": "형식 오류일 때 API 는 어떤 상태 코드와 본문을 돌려줘야 하는가? 현재 다른 검증 오류 응답 규약이 계약에 없다.",
     "impact": "계약 파일, 웹의 오류 표시 방식, AC-02 와 AC-03 을 결정한다.",
     "resolution": {
       "answer": "422 로 하고 본문은 {\"errors\":[{\"field\":\"email\",\"code\":\"invalid_format\"}]} 형태. 웹은 code 를 보고 문구를 고른다.",
       "source": {"kind": "user_message", "reference": "local session: Q-01 답변", "excerpt": "422로 하고 errors 배열에 field랑 code 넣어줘. 문구는 프론트에서 code 보고 정해"},
       "acceptance_ids": ["AC-02", "AC-03"]}}
  ]
}
```

## 6. 진행

```console
python -m web_pipeline clarification-report --task SIGNUP-014
python -m web_pipeline prepare --task SIGNUP-014 --implementer claude
python -m web_pipeline run --task SIGNUP-014 --profile Baseline
python -m web_pipeline transition --task SIGNUP-014 --status READY
python -m web_pipeline transition --task SIGNUP-014 --status IN_PROGRESS
python -m web_pipeline run --task SIGNUP-014 --profile Fast
python -m web_pipeline transition --task SIGNUP-014 --status VERIFYING
python -m web_pipeline run --task SIGNUP-014 --profile Task
python -m web_pipeline transition --task SIGNUP-014 --status REVIEW
python -m web_pipeline review --task SIGNUP-014 --decision Docs/Work/SIGNUP-014/review-decision.json
python -m web_pipeline transition --task SIGNUP-014 --status DONE
python -m web_pipeline validate --task SIGNUP-014
```

- `clarification-report` 는 `CLEAR`(exit 0)여야 한다. `prepare` 이후 task 문서·설정·인용 문서를 고치면 fingerprint 가 stale 이 되어 `revise --reason` 부터 다시 한다.
- Baseline 은 코드 변경 **전**에 실행한다. 새 테스트는 아직 없으므로 기존 check 결과가 기록된다. policy check 가 아닌 check 의 실제 FAIL 은 Baseline 으로 남을 수 있다(exit 1 이어도 `STATE.md` 의 `baseline_run` 이 채워졌는지 본다).
- 구현은 IN_PROGRESS 에서 한다: 계약 → API + 테스트 → 웹 + 테스트. `Fast` 는 필요할 때마다 반복한다.
- 완료 프로필은 scopes 가 있으므로 `Task` 다(`verification-plan --task SIGNUP-014` 의 `profile` 로 확인. scopes 가 없으면 `Full`). 이 예시의 `verification-plan` 은 `level: "project"` 와 `reasons: ["broad input: contracts/signup.schema.json", "unknown or ambiguous impact: contracts/signup.schema.json"]` 를 보인다. `contracts/*` 가 `broad_paths` 이고 어느 component 에도 속하지 않아 두 component 의 Task check 가 모두 실행된다는 뜻이며 오류가 아니다. frontend 도메인이므로 이 run 의 `browser-e2e` 가 `screenshots/manifest.json`(desktop 1440x900, mobile 390x844)을 남겨야 한다. 완료 run 이후 소스를 바꾸면 REVIEW 전이가 거부된다.

## 7. 리뷰 decision (`review --decision`)

REVIEW 상태에서 `pipeline-reviewer` 서브에이전트가 diff 와 완료 run 의 `summary.json`·로그를 읽고 작성한다. 네 필드 모두 필수, 문자열은 공백만으로 채울 수 없고 `alternatives` 는 1개 이상이다. 이는 사람의 승인이 아니다. 문제가 있으면 기록하지 말고 `transition --status IN_PROGRESS` 로 되돌려 고친다.

```json
{
  "choice": "SIGNUP-014 r1 의 구현을 승인 없이 로컬 self-review 로 수락한다.",
  "rationale": "Task run 의 web-unit, browser-e2e, contract-provider, contract-consumer, integration 이 모두 PASS 이고 AC-01~03 의 시나리오(빈 값, 255자, 공백, 직접 API 호출)가 테스트에 있다. 422 본문이 계약 파일과 일치하고 서버 검증이 클라이언트와 독립적이다. diff 는 BRIEF 범위 안이다.",
  "alternatives": ["클라이언트 검증만 추가: 직접 API 호출을 막지 못해 기각", "400 재사용: Q-01 사용자 답변(422)과 달라 기각"],
  "risks": ["규칙이 RFC 5322 전체보다 좁아 드문 유효 주소(따옴표 local-part)를 거부한다. BRIEF 의 합의된 규칙이다."]
}
```

## 8. 큐로 실행할 때의 plan (`loop start --plan`)

후속 task `SIGNUP-015`(오류 문구 다국어화)를 `new` 로 만들어 둔 뒤 두 task 를 큐에 넣는 예. 큐를 쓰면 6절의 `run`/`transition` 은 `loop next` 가 수행하고, 에이전트는 `PLAN`/`IMPLEMENT`/`REVIEW` action 만 처리한다([continuous.md](continuous.md)).

```json
{
  "objective": "가입 폼 이메일 형식 검증과 오류 문구 다국어화를 순서대로 완료한다.",
  "tasks": [
    {"task_id": "SIGNUP-014", "depends_on": []},
    {"task_id": "SIGNUP-015", "depends_on": ["SIGNUP-014"]}
  ],
  "completion_gate": "queue",
  "max_steps": 60,
  "elapsed_minutes": 180
}
```

`depends_on` 은 "그 task 가 유효하게 DONE" 이라는 뜻이고 큐 안의 id 만 가리킬 수 있다. `completion_gate: "merge"` 는 큐 완료 시 merge gate 검증까지 요구한다.

## 9. 보고에 넣을 것

task id/revision, 최종 상태, 실행된 check 와 결과, 증거 경로(`Reports/Pipeline/<run-id>/summary.json`), Baseline 에서 이미 실패하던 check, 남은 승인(이 예시는 없음).
