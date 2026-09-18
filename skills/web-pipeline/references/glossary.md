# Glossary

엔진이 출력하거나 파일에 기록하는 토큰과 용어. 토큰은 원문 그대로 비교한다.

## Task status (`STATE.md` 의 `status`)

| 토큰 | 의미 |
|---|---|
| `DRAFT` | 계획 단계. `prepare` 와 `Baseline` 만 가능. `revise` 의 도착 상태 |
| `READY` | 문서·fingerprint·Baseline·design 승인이 유효. 구현 시작 가능 |
| `IN_PROGRESS` | 구현 중. `Fast`/completion run 가능 |
| `VERIFYING` | 구현 종료, completion run 대기/실행 |
| `REVIEW` | completion run PASS + 현재 트리와 일치. review gate 대기 |
| `DONE` | 종착 상태. 변경하려면 `revise` |
| `BLOCKED` | 수동 보류. `READY` 또는 `IN_PROGRESS` 로만 복귀 |

`release_status`: `NOT_READY`(기본) · `READY`(`Release` run PASS 시 엔진이 설정) · `VERIFIED`(스키마 허용값, 엔진은 설정하지 않음).

## Check / run 결과 (`summary.json`)

| 토큰 | 의미 |
|---|---|
| `PASS` | exit 0 + log 존재 (+ test report/artifact 검증 통과) |
| `FAIL` | nonzero exit, `timeout`, 잔류 자식 프로세스, 증거 검증 실패 |
| `NOT_RUN` | reason `missing, disabled, or not enabled for profile` — config 문제 |
| `BLOCKED` | 실행 자체 불가. `blocker_kind`: `external`(spawn/정책 오류) · `budget`(active-time 소진) |
| `NOT_APPLICABLE` | 해당 check 에 유효한 exception 승인이 있을 때만. PASS 를 만들어내지 않음 |
| `INCONCLUSIVE` | 스키마 허용값. 엔진은 생성하지 않음 |

run `status` 집계: 전부 `PASS`/`NOT_APPLICABLE` → `PASS`; `FAIL` 하나라도 → `FAIL`; 아니면 `BLOCKED`; 그 외 `NOT_RUN`.
엔진 합성 check id: `source-stability`, `browser-screenshots`, `required-artifacts`, `runner`.
test report 의 test status: `passed` `failed` `error` `skipped`.

## 명령 결과 status

| 토큰 | 출처 |
|---|---|
| `PASS` / `FAIL` | `validate`, `run`, `init`; `FAIL` 은 모든 오류 envelope |
| `RECORDED` | `review`, `approve` |
| `ARCHIVED` / `RECOVERED` | `archive` / `archive --recover`, `loop recover` |
| `STARTED` `IDLE` `BUSY` `PAUSED_LIMIT` `WAITING` `ACTION_REQUIRED` `CONTINUE` `COMPLETE` `RENEWED` | `loop` (아래) |

## Loop

| 토큰 | 의미 |
|---|---|
| `STARTED` | `loop start` 성공. checkpoint = `Docs/Work/AUTOPILOT.json` |
| `IDLE` / `BUSY` / `PAUSED_LIMIT` | `loop status`: lease 없음 / lease 있음 / queue 한도 도달 |
| `ACTION_REQUIRED` | 에이전트 행동 필요. `token` 포함 |
| `CONTINUE` | 확인 응답. task 완료가 아님 → `loop next` |
| `WAITING` | 진행 가능한 task 없음. `tasks[].reason` 또는 `scope: workspace` |
| `COMPLETE` | 전 task DONE + policy (+ `merge` gate) 통과 |
| `RECOVERED` / `RENEWED` | lease 해제 / budget 추가. 둘 다 `budgets_reset: false` |
| action (에이전트) | `PLAN` `IMPLEMENT` `REPAIR` `REVIEW` |
| action (엔진) | `Baseline` `READY` `IN_PROGRESS` `Fast` `VERIFYING` `Task` `Phase` `Full` `DONE` |
| cursor | `IMPLEMENT` → `FAST` → `FULL`; 검증 실패·`changes_required` 시 `REPAIR` |
| outcome | `prepared` `implemented` `reviewed` `changes_required` `blocked` |
| event kind | `START` `SELECT` `EXECUTED` `WAIT` `WAITING` `DECISION` `RECOVER` `RETRY` `RECONCILE` `RENEW` `LEASE_END` |
| `completion_gate` | `queue`(기본) · `merge`(모든 활성 task DONE + 정리된 checkout 요구) |
| lease / token | `loop next` 가 에이전트 행동에 발급하는 단일 점유권. revision, state hash, fingerprint, tree digest 에 묶임. token 은 `complete`/`recover` 에 그대로 전달 |
| waiting | 큐 item 에 저장된 차단 사유. `loop retry` 로만 해제 |

## Clarification (`clarification-report`)

| 토큰 | 의미 |
|---|---|
| `CLEAR` | 기록된 분석·질문이 모두 해결됨. READY 나 승인을 뜻하지 않음 |
| `NEEDS_INPUT` | `errors[]` 에 미해결 질문/불완전 분석. 사용자에게 묻는다 |
| `NOT_CONFIGURED` | `planning_version` 없는 legacy task. `revise` 로 활성화 |
| source kind | `document`(파일 + excerpt 일치 필수) · `user_message`(사용자 발언 전사) |

## Approval

| 토큰 | 의미 |
|---|---|
| `NO_APPROVAL_REQUIRED` | 이 phase 에 승인 역할 없음. 묻지 말고 진행 |
| `AWAITING_USER` | 기존 동의·현재 STATE·증거를 먼저 확인하고 전사/복구. 실제 새 결정이 남을 때만 질문 |
| `SATISFIED` | 이미 유효한 승인 존재. 다시 묻지 않음 |
| phase | `design`(구현 전) · `review`(REVIEW 에서) · `release`(DONE T4) · `exception`(`--check-id` 단위) |
| `APPROVED` | 레코드 `outcome` 의 유일한 허용값 |
| `user_approval` / `local_transcription` | receipt 의 `kind` / `assurance`. 서명·신원 증명이 아님 |
| `self_review` | `LOCAL_REVIEW-<digest>.json` 의 kind. 사람 승인이 아님 |
| ADR `PROPOSED` / `ACCEPTED` | gate 는 `ACCEPTED` 만 인정. T3/T4 와 보호 변경에 필수 |
| standard policy | 비보호 T0–T2 는 승인 없음(T1/T2 는 self-review). 그 외는 사용자 receipt. trust 파일 불필요 |
| strict policy | 모든 승인이 Ed25519 서명 + 프로젝트 외부 trust 파일(`--trust`/`WEB_PIPELINE_TRUST`). `approval_policy` 누락 시 기본값 |
| receipt | `USER_APPROVAL-<hash>.json`. task/revision/fingerprint(+review·release 는 tree digest, run id, run digest)에 묶인 사용자 동의 전사본 |

## Boundary / scope / legacy

| 토큰 | 의미 |
|---|---|
| `NOT_CONFIGURED` (boundaries) | config 에 `boundaries` 없음. `validate` 경고, import 격리 미증명 |
| `CONFIGURED` | `inspect` 의 boundaries 상태 |
| selection `level` | `task` · `phase` · `project`(전체로 확장됨, `reasons` 참조) · `legacy`(scopes 미설정) |
| legacy accounting | `budget_version` 이 1 이 아닌 task/queue. `loop renew` 로만 이관 |
| Project `NOT_READY` | `project.mode != project` 또는 `project.ready != true` |

## Maintenance

| 토큰 | 의미 |
|---|---|
| `PREVIEW` | `init --preview`, `upgrade`(`--apply` 없음). `writes: false` |
| `APPLIED` | 업그레이드 적용. `transaction` id 반환 |
| `UNCHANGED` | 변경할 관리 파일 없음 |
| `RESTORED` | `restore` 완료. backup 은 유지 |
| 트랜잭션 status | `PREPARED` → `APPLIED`; 복원 시 `RESTORING` → `RESTORED` |
| managed files | `web_pipeline/`, `Schemas/`, `Scripts/` 중 `.pipeline-install.json` 에 해시가 기록된 엔진 파일 |
| `project_owned` | 프로젝트가 `Scripts/` 아래에 추가한 파일. 업그레이드·복원이 건드리지 않는다 |

## Risk tier

최종 tier = max(요청 tier, 도메인 floor, 보호 규칙 tier, path rule, migration floor). 내려가지 않는다.

| Tier | 기본 floor 도메인 | 요구 |
|---|---|---|
| `T0` | frontend | BRIEF, DOR, ACCEPTANCE, CLARIFICATIONS. standard 에서 review 없음 |
| `T1` | backend | + self-review(standard) / Reviewer(strict) |
| `T2` | database, api, external_integration | + `PLAN.md` |
| `T3` | authentication, authorization, security, privacy, infrastructure | + `EXEC_PLAN.md`, ACCEPTED ADR, 사람 승인, 프로젝트 전체 검증 |
| `T4` | payment, deployment | + `RELEASE.md`, `Release` 프로필, release 승인 |

## 용어

| 용어 | 정의 |
|---|---|
| fingerprint | config 전체 + `sources` 문서 + task 문서 + ADR + scope 필드(tier, domains, protected, migration, base_ref, implementer, revision) 의 해시. `prepare` 가 기록. 하나라도 바뀌면 stale |
| tree digest | report root, `Docs/Work`, `Docs/Archive`, `generated_paths`, 캐시 디렉터리를 제외한 **작업 트리 전체 파일**의 바이트 해시. 추적되지 않은 파일도 포함하되, `project.respect_gitignore: true`(기본)면 Git 이 무시하는 미추적 파일은 제외 |
| snapshot | `{commit, tree_digest, dirty}`. run 과 승인이 묶이는 대상은 `tree_digest` |
| policy snapshot | `risk`, `verification`, `evidence`, `iteration_limits`, `boundaries` 의 해시. 바뀌면 기존 run 무효 |
| revision | `revise` 마다 +1. 승인·run·fingerprint 는 revision 에 묶임 |
| run id / evidence | `Reports/Pipeline/<run_id>/` (`summary.json`, `logs/`, `artifacts/`, `screenshots/`). 파일은 해시로 고정되며 수정 금지 |
| Baseline | 변경 전 상태의 증거. DRAFT 에서만 캡처 |
| completion run | `full_run`. completion 프로필 또는 `Full` 의 PASS run |
| protected change | `risk.protected_rules` 의 키(예: `authentication`, `database_schema`, `payment`). 역할 승인 + ADR scope 필요 |
| domain | 12개 고정 어휘. `project.supported_domains` 는 그 부분집합 |
| budget | task: `iteration_limits`(`total_attempts` 5, `same_failure` 3, `external_retries` 2, `elapsed_minutes` 120). queue: `max_steps`, `elapsed_minutes`. 누적 시간은 새 도입 `time_budget_mode: warn`에서 경고, 기존 미지정은 enforce |
| renewal | `loop renew` 가 남기는 가산 기록. 카운터를 리셋하지 않으며 `same_failure`/`external_retries` 는 풀지 않는다 |
| Phase task | `SCOPE.json` `level: phase`. DONE member 들의 check 합집합을 현재 트리에서 재검증 |
| implementation group | plan 의 `{phase, order}`. member 전원이 Baseline/진입 gate 를 마친 뒤 `order` 순으로 구현 |
| migration class | `none` T0 · `reversible` T2 · `backward_compatible` T3 · `destructive`/`irreversible` T4. `none` 외에는 `database_schema`, 뒤 둘은 `destructive_migration` 보호 변경이 자동 추가 |
| exception | 특정 check 를 `NOT_APPLICABLE` 로 만드는 승인 레코드(`Tech Owner` + 관련 보호 역할, `reason` 필수) |
| execution label | `--implementer`/`--worker` 값(기본 `claude`). 사람 신원이 아님 |
