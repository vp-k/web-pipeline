# Commands & Lifecycle

모든 프로젝트 명령은 프로젝트 루트에서 `python -m web_pipeline <command>` 로 실행한다 (`--root` 기본값 `.`).
출력은 stdout JSON. 실패는 stderr `{"status":"FAIL","error":"..."}` + exit 1. 인자 오류(argparse)는 exit 2.

## 1. Task 상태 다이어그램

```
new ─► DRAFT ─(transition READY)─► READY ─(IN_PROGRESS)─► IN_PROGRESS ─(VERIFYING)─► VERIFYING
        ▲                                                   ▲                           │ (REVIEW)
        │ revise (어느 상태에서든, revision+1)                 └──(IN_PROGRESS: 재작업)── REVIEW ─(DONE)─► DONE ─► archive
        │
   모든 비-DONE 상태 ─(BLOCKED)─► BLOCKED ─(READY | IN_PROGRESS)─► 복귀
```

| 전이 | 명령 | 통과해야 하는 gate |
|---|---|---|
| (없음)→DRAFT | `new` | task_id 형식, tier/domains 유효, 아카이브 이력 없는 id |
| DRAFT 봉인 | `prepare` | 문서 완비(placeholder 없음), CLARIFICATIONS `CLEAR`, ACCEPTANCE의 check가 enabled + `Full`/`Policy` 프로필, `base_ref` 존재 → `fingerprint`/`implementer` 기록 |
| DRAFT 증거 | `run --profile Baseline` | fingerprint 최신, DRAFT 상태 → `baseline_run` 기록 |
| DRAFT→READY | `transition --status READY` | project 모드(kit 불가), 문서 완비, implementer, fingerprint 최신, 유효한 Baseline, design 승인(필요 시) |
| READY→IN_PROGRESS, →VERIFYING | `transition` | 위 gate 전부 재검증 |
| VERIFYING→REVIEW | `transition --status REVIEW` | completion run(`full_run`) PASS + **현재 트리와 일치**, 모든 acceptance check가 PASS/NOT_APPLICABLE |
| REVIEW→DONE | `transition --status DONE` | 위 + review gate: standard 비보호 T1/T2 = `review` 기록, T0 = 없음, 그 외 = Reviewer 승인 |
| REVIEW→IN_PROGRESS | `transition --status IN_PROGRESS` | `full_run`/`release_run` 초기화, 완료 검증 재실행 필요 |
| *→BLOCKED | `transition --status BLOCKED` | 분류 오류만 검사 |
| *→DRAFT | `revise --reason` | `transition --status DRAFT` 는 거부됨. revision+1, fingerprint·approvals·exceptions·모든 run 포인터 초기화 (iteration 카운터는 유지) |

DONE 은 종착 상태다. DONE 이후 변경은 `revise` 로만 가능하다.

## 2. 최소 시퀀스 (standard, 비보호 T0–T2)

| # | 명령 / 작업 | 에이전트가 작성할 파일 (`Docs/Work/<TaskId>/`) |
|---|---|---|
| 1 | `new --task <id> --title "<t>" --tier T1 --domains frontend,backend --base-ref <commit>` | 엔진 생성: `STATE.md`, `BRIEF.md`(TBD), `DOR.md`, `ACCEPTANCE.json`(`{"criteria":[]}`), `CLARIFICATIONS.json`(빈 템플릿), T2+ `PLAN.md`, T3+ `EXEC_PLAN.md`, T4 `RELEASE.md` |
| 2 | 계획 문서 작성 | `BRIEF.md`, `DOR.md`, (T2) `PLAN.md`: 단독 줄 `TBD`/`TODO`/`UNSET` 제거. `ACCEPTANCE.json`, `CLARIFICATIONS.json` 채움. 선택: `DOD.md`, `SCOPE.json` |
| 3 | `clarification-report --task <id>` | `CLEAR`(exit 0) 가 될 때까지 질문을 사용자에게 묻고 resolution 기록 |
| 4 | `prepare --task <id> --implementer claude` | 이후 task 문서·config·source 문서를 바꾸면 fingerprint stale |
| 5 | `run --task <id> --profile Baseline` | 코드 변경 **전** 실행. 비-policy check 의 FAIL 은 허용(캡처됨), exit 1 이어도 STATE 의 `baseline_run` 이 채워졌으면 성공 |
| 6 | `transition --task <id> --status READY` → `--status IN_PROGRESS` | — |
| 7 | 구현, 필요 시 `run --profile Fast` 반복 | 제품 코드 |
| 8 | `transition --status VERIFYING` → `run --profile <completion>` | completion = `verification-plan --task <id>` 의 `profile` |
| 9 | `transition --status REVIEW` | run 이후 소스를 바꾸지 않는다 |
| 10 | T1/T2: `review --task <id> --decision <file>` (T0 생략) | decision JSON (§6) |
| 11 | `transition --status DONE` → `validate --task <id>` → `archive --task <id>` | — |

파일 요건:
- `ACCEPTANCE.json`: `{"criteria":[{"id","description","checks":["<command id>",...]}]}` — criteria ≥1, id 유일, checks ≥1, 모두 config 의 enabled command.
- `CLARIFICATIONS.json`: `schema_version "1.0"`, `task_id`, `revision`(현재 값), `analysis` 6개 영역(`goal_scope`,`user_flow`,`exceptions`,`data_integrations`,`constraints`,`acceptance`) 각각 `finding` + `sources` ≥1, `questions[].resolution` 은 `null` 금지(`answer`,`source`,`acceptance_ids`). source = `{"kind":"document"|"user_message","reference","excerpt"}`; `document` 는 파일이 존재하고 excerpt 가 그 안에 그대로 있어야 한다.
- `SCOPE.json` (`verification.scopes` 설정 시에만): `{"level":"task"|"phase","components":[...],"members":[...]}` — `phase` 는 members ≥1, `task` 는 members 0.
- 보호 변경/T3+: `attach --kind adr` 는 `prepare` 전에, 승인은 `approval-request` → 사용자 동의 → `approve` (design 은 READY 전, review 는 REVIEW 에서).

## 3. 명령 표

| 명령 | 목적 | 쓰기 | 주요 플래그 | exit |
|---|---|---|---|---|
| `status` | 엔진 버전, mode/ready, approval policy, 전체 task, lock, queue, `next` 힌트 | 아니오 | `--task` | 0 |
| `locks` | `.pipeline-locks/*.lock` 의 pid/started_utc/alive | `--clear-stale` 만 | `--clear-stale` | 0 |
| `validate` | 정책 gate 검사 | 아니오 | `--task`, `--gate progress\|merge`, `--base-ref`, `--kit`, `--trust` | PASS=0, FAIL=1 |
| `new` | task 생성 | 예 | `--task --title --domains`(필수) `--tier`(기본 T1) `--protected --migration --base-ref` | 0 |
| `prepare` | DRAFT 봉인(fingerprint) | 예 | `--task`, `--implementer` | 0 |
| `clarification-report` | 계획 질문 진단 | 아니오 | `--task` | `CLEAR`=0, 그 외 1 |
| `run` | 검증 프로필 실행 | 예 | `--task --profile`, `--run-id`, `--trust` | PASS=0, 그 외 1 |
| `verification-plan` | 실행될 check/scope 미리보기 | 아니오 | `--task`, `--profile` | 0 |
| `fingerprint` | 현재 fingerprint 계산 | 아니오 | `--task` | 0 |
| `transition` | 상태 전이 | 예 | `--task --status`, `--trust` | 0 |
| `revise` | DRAFT 로 되돌리고 revision+1 | 예 | `--task --reason` | 0 |
| `review` | self-review 기록 (standard 비보호 T1/T2, REVIEW 상태) | 예 | `--task --decision <json>` | 0 |
| `approval-request` | 필요한 사용자 승인 범위 조회 | 아니오 | `--task --phase design\|review\|release\|exception`, `--check-id` | 0 |
| `approve` | 사용자 동의를 receipt 로 기록 | 예 | `--task --record <json>` | 0 |
| `attach` | adr/approval/exception 레코드 등록(승인 아님) | 예 | `--task --kind --path` | 0 |
| `archive` | DONE task 를 `Docs/Archive/<id>-r<rev>` 로 이동 | 예 | `--task` \| `--recover`, `--include-members` | 0 |
| `init` | 프로젝트에 엔진 도입 (kit 쪽 엔진에서 실행) | 예 | `--target`, `--preview`, `--domains a,b`, `--ci` | 0 |
| `inspect` | 도입/도구 진단 | 아니오 | `--target` | 0 |
| `upgrade` | 관리 엔진 파일 업그레이드 (kit 쪽 엔진에서 실행) | `--apply` 만 | `--target`, `--baseline`, `--apply` | 0 |
| `restore` | 업그레이드 트랜잭션 복원 | 예 | `--target --transaction` | 0 |
| `loop start` | 큐 생성 | 예 | `--plan <json>` | 0 |
| `loop status` | 큐/lease/budget 조회 | 아니오 | — | 항상 0 (읽기 전용) |
| `loop next` | 다음 행동 선택·기계 단계 자동 실행 | 예 | `--worker` | `WAITING`/`BUSY`/`PAUSED_LIMIT`/`FAIL`=1 |
| `loop complete` | 에이전트 행동 결과 보고 | 예 | `--token --outcome --decision <json>` | 0 |
| `loop recover` | 중단된 lease 해제(재실행 안 함) | 예 | `--token --reason` | 0 |
| `loop retry` | 외부 조건이 풀린 뒤 waiting 해제 | 예 | `--task --reason` | 0 |
| `loop reconcile` | `revise` 된 task 를 큐에 다시 수용 | 예 | `--task --reason` | 0 |
| `loop renew` | 사용자가 승인한 추가 예산 | 예 | `--task` \| `--queue`, `--reason`, `--extra-minutes`, `--extra-attempts` | 0 |

check 명령의 `argv[0]` 는 PATH/PATHEXT 로 해석되므로 Windows 에서도 `npm`, `npx`, `pnpm` 을 `.cmd` 없이 쓴다.

## 4. Verification 프로필

| 프로필 | 허용 상태 | 용도 | 포인터 |
|---|---|---|---|
| `Policy` | DRAFT 제외 | `policy_checks` 만. 시도 횟수 미차감 | — |
| `Baseline` | DRAFT (prepare 후) | 변경 전 증거. policy check 는 PASS 필수, 나머지는 실제 실행된 FAIL 허용. DRAFT 이후 동결 | `baseline_run` |
| `Fast` | IN_PROGRESS, VERIFYING | 빠른 피드백 | — |
| `Task` | IN_PROGRESS, VERIFYING | scopes 설정 + task 수준 scope 의 completion | `full_run` |
| `Phase` | IN_PROGRESS, VERIFYING | `SCOPE.json` level `phase` 의 completion. members 전원 DONE 필요 | `full_run` |
| `Full` | IN_PROGRESS, VERIFYING | 프로젝트 전체. scopes 미설정 시 completion. 항상 completion 으로 인정됨 | `full_run` |
| `Release` | DONE + T4 | 현재 completion 증거 + release 승인 필요 | `release_run`, `release_status=READY` |

- completion 프로필: `verification.scopes` 없음 → `Full`; 있음 → `Phase`(SCOPE level phase) 또는 `Task`.
- Fast/Task/Phase/Full 은 실행 전 policy gate 와 budget 을 검사하고 attempt 를 1 차감한다(PASS 면 failed_attempts 환불). completion 프로필 시작 시 기존 `full_run` 은 지워진다.
- T3/T4, 보호 변경, broad path(`pipeline.config.yaml`, `package.json`, lock 파일 등), 소유 component 가 모호한 경로는 scope 를 프로젝트 전체로 확장한다.

## 5. `loop` 자동 진행

```
loop start --plan plan.json
repeat:
  loop next --worker claude
    ACTION_REQUIRED → action 수행 → loop complete --token <t> --outcome <o> --decision d.json → (CONTINUE) → 다시 next
    COMPLETE        → 종료
```

`loop next` 는 Baseline, READY, IN_PROGRESS, Fast, VERIFYING, completion run, REVIEW 전이, DONE 을 스스로 실행하고, 에이전트가 필요한 지점에서만 멈춘다.

| `action` | 할 일 | 허용 outcome |
|---|---|---|
| `PLAN` | task 문서 작성 후 직접 `prepare` 실행 | `prepared`, `blocked` |
| `IMPLEMENT` / `REPAIR` | 제품 코드만 수정. task 문서·STATE 변경, 수동 `run`/`transition` 금지 | `implemented`, `blocked` |
| `REVIEW` | 소스를 바꾸지 않고 completion 보고서와 diff 검토 | `reviewed`(T1/T2 는 decision 이 self-review 로 기록됨), `changes_required`(→IN_PROGRESS, REPAIR), `blocked` |

| `loop next` status | 의미 | 대응 |
|---|---|---|
| `ACTION_REQUIRED` | lease 발급(`token`,`task_id`,`action`) | 수행 후 `loop complete`. 턴을 끝내지 않는다 |
| `CONTINUE` | (`complete`/`retry`/`reconcile` 응답) 확인일 뿐 | `loop next` |
| `COMPLETE` | 모든 task DONE + gate 통과 | 보고, 필요 시 `archive` |
| `WAITING` | `scope: workspace`(미완료 Git 작업) 또는 `tasks[].reason` | 원인 해결(승인, 의존성, BLOCKED 등) 후 `loop retry --task --reason` → `next` |
| `BUSY` | 끝나지 않은 lease 존재 | `loop status` 로 token 확인 → `complete`, 또는 프로세스 점검 후 `loop recover` → `loop retry` |
| `PAUSED_LIMIT` | queue/task budget 소진 | 사용자에게 보고. 사용자가 승인하면 `loop renew`. 자체 갱신 금지 |
| `FAIL` | stderr 오류 | `troubleshooting.md` |

revision 이 바뀐 task 는 `loop reconcile` 전까지 진행되지 않는다. 완료된 큐는 다음 `loop start` 때 `Docs/Work/AUTOPILOT-<queue_id>.json` 으로 보존된다.

## 6. JSON 형식

plan (`loop start --plan`):
```json
{"objective": "왜 이 큐를 도는가",
 "tasks": [{"task_id": "A-001", "depends_on": []}, {"task_id": "A-002", "depends_on": ["A-001"]}],
 "completion_gate": "queue", "max_steps": 100, "elapsed_minutes": 120,
 "implementation_groups": [{"phase": "PH-1", "order": ["A-001", "A-002"]}]}
```
필수는 `objective`, `tasks` 뿐. `completion_gate`: `queue`(기본) | `merge`. 기본 `max_steps` 100, `elapsed_minutes` 120. 큐에 넣는 Phase 는 모든 member 를 `depends_on` 에 명시해야 한다. `implementation_groups` 는 scopes 설정, order ≥2, 전원 DRAFT + prepare 완료가 조건이다.

decision (`loop complete --decision`, `review --decision`):
```json
{"choice": "무엇을 결정했는가", "rationale": "근거", "alternatives": ["검토한 대안 ≥1"], "risks": []}
```
모든 문자열은 공백만으로 채울 수 없다. `blocked` outcome 에서는 `rationale` 이 waiting 사유로 기록된다.
