# Troubleshooting

오류는 stderr 의 `{"status":"FAIL","error":"..."}` (exit 1), check 의 `reason`, 또는 `loop next` 의 `tasks[].reason` 으로 나온다. 아래 문자열(또는 고정 접두부)로 찾는다.
먼저 볼 것: `python -m web_pipeline status` · `python -m web_pipeline validate --task <id>` · `Reports/Pipeline/<run_id>/summary.json` 과 `logs/`.

## 설정 / 프로젝트 준비

| 문자열 | 원인 | 복구 |
|---|---|---|
| `Project is NOT_READY; configure sources, commands and Git baseline` | `project.mode` 가 `project` 가 아니거나 `project.ready` 가 `true` 가 아님 | `pipeline.config.yaml` 에서 `sources`, `verification.commands`, `project.supported_domains` 를 채우고 첫 commit 후 `ready: true` → `python -m web_pipeline validate` |
| `Required project command <id> is disabled` | `policy_checks` 또는 지원 도메인의 필수 check 가 `enabled: false` | `verification.commands[]` 의 해당 id 에 `enabled: true` + 실제 `argv`. 쓰지 않는 도메인이면 `supported_domains` 에서 제거 |
| `<label>/<profile>: <check> cannot execute in required profile` | 필수 check 의 `profiles` 에 해당 프로필 없음 | 그 check 의 `profiles` 에 프로필 추가 |
| `Configuration must be JSON-compatible YAML` | config 는 JSON 문법만 허용 | YAML 전용 문법(주석, 따옴표 없는 키) 제거 |
| `compound shell execution forbidden for <id>; use an explicit script file` | `argv` 가 `cmd`, `sh -c`, `powershell -Command` 등 | 도구를 직접 호출(`["npm","run","lint"]`)하거나 `["pwsh","-NoProfile","-File","Scripts/x.ps1"]` / `["bash","Scripts/x.sh"]` |
| `A ready project requires Git history to inspect output exclusions` | commit 없는 저장소 | `git init` → `git add -A` → `git commit` |
| `Output exclusion contains tracked source: <name>` | `generated_paths`/report root 안에 Git 추적 파일 존재 | `git rm -r --cached <path>` + commit, 또는 그 경로를 `generated_paths` 에서 제거 |
| `Output exclusions cannot hide governance or source documents` | 제외 경로가 `Docs/`·`sources` 문서를 덮음 | `generated_paths` 를 빌드 산출물 디렉터리로 한정 |
| `Link paths are forbidden: <rel>` | 경로에 symlink/junction | 실제 디렉터리로 교체. `pnpm` 링크 등은 `node_modules` 안에만 둔다 |

## 상태 파일 / 잠금 / 유지보수

| 문자열 | 원인 | 복구 |
|---|---|---|
| `STATE.md must contain exactly one state block` / `Invalid state JSON` | STATE.md 를 손으로 편집해 블록이 깨짐 | `git checkout -- Docs/Work/<id>/STATE.md` 로 마지막 정상본 복원. 값을 직접 고치지 않는다 |
| ``Another operation holds lock <name> (pid N, since <utc>); run `locks` to inspect it`` | 살아 있는 다른 엔진 프로세스가 같은 작업을 잡고 있다(죽은 프로세스의 락은 자동 회수되므로 보통 실제 실행 중) | `python -m web_pipeline locks` → `alive: true` 면 끝날 때까지 대기. `false` 로 남아 있다면 `locks --clear-stale` |
| `Engine maintenance is active; retry after it completes` | `.pipeline-locks/upgrade.lock` 존재 | upgrade/restore 종료 대기. 죽은 PID 면 `locks --clear-stale` 후 `upgrade`/`restore` 상태 확인 |
| `Interrupted archive requires archive --recover before continuing` | `Docs/Work/ARCHIVE_PENDING.json` 잔존 | `python -m web_pipeline archive --recover` 후 archive 재시도 |
| `Unfinished Git integration: <marker>...` | merge/rebase/cherry-pick/revert 미완료, unmerged index | 충돌 해결 후 `git merge --continue` 등으로 마치거나 사용자 확인 후 `--abort`. 변경을 버려서 우회하지 않는다 |

## prepare / transition

| 문자열 | 원인 | 복구 |
|---|---|---|
| `missing or empty required task document: <name>` | tier 에 필요한 문서 없음(T2+ `PLAN.md`, T3+ `EXEC_PLAN.md`, T4 `RELEASE.md`) | 문서를 실제 내용으로 작성 → `prepare` |
| `unfilled template placeholder in required task document: <name>` | `TBD`/`TODO`/`UNSET` 만 있는 줄 | 그 줄을 실제 내용으로 교체 |
| `ACCEPTANCE.json must contain populated criteria with checks` / `acceptance references unknown checks: [...]` | 기준에 check 가 없거나 config 에 없는 id | 각 criterion 의 `checks` 를 `verification.commands` 의 id 로 |
| `Acceptance check <id> must be enabled and executable in Full` | 참조 check 가 disabled 이거나 `profiles` 에 `Full` 없음 | config 에서 enable + `Full` 추가 |
| `project tasks require an explicit Git base_ref` | `new` 시 `--base-ref` 누락 | `base_ref` 를 바꾸는 명령은 없다. 다른 id 로 `python -m web_pipeline new --task <id2> ... --base-ref <ref>` |
| `cannot inspect diff from base_ref '<ref>': ...` | ref 가 저장소에 없음 | `git rev-parse <ref>` 로 확인 후 fetch. ref 자체가 틀렸으면 올바른 `--base-ref` 로 새 task |
| `base_ref '<ref>' must be a git revision, not an option` | `-`로 시작하는 값(`--output=…` 등)을 base_ref 로 넘김 | 커밋 해시·브랜치·태그만 쓴다 |
| `only DRAFT tasks can be prepared; revise the task first` | DRAFT 가 아님 | `python -m web_pipeline revise --task <id> --reason "<why>"` → `prepare` |
| `task fingerprint is stale; revise the task` / `<id>: source fingerprint is stale` / `task must be prepared with a current fingerprint; revise after changing scope or docs` | `prepare` 이후 config, `sources` 문서, task 문서, ADR, 분류(path rule 승격 포함)가 변함 | 의도한 변경이면 `revise` → `prepare` → Baseline 부터. 의도하지 않았으면 그 파일을 되돌린다 |
| `READY requires a Baseline run` / `Baseline run is required` | Baseline 미캡처 | DRAFT 에서 `python -m web_pipeline run --task <id> --profile Baseline` |
| `Baseline is frozen after DRAFT; revise the task before recapturing it` | DRAFT 밖에서 Baseline 시도 | 변경 후 재캡처는 금지. 정말 필요하면 변경을 분리(stash/branch)하고 `revise` |
| `<Profile> requires IN_PROGRESS or VERIFYING state` / `<Profile> is forbidden while task is DRAFT` | 상태와 프로필 불일치 | `status --task <id>` 의 `next` 를 따른다 |
| `invalid transition: A -> B` / `Use revise to return to DRAFT and increment revision` | 허용되지 않는 전이 | 전이표대로 한 단계씩. DRAFT 복귀는 `revise` 뿐 |
| `T3/T4 task requires an accepted ADR` / `protected scope lacks an accepted ADR: [...]` / `ADR is not ACCEPTED: ` / `stale or mismatched ADR: ` | ADR 없음·`PROPOSED`·scope 부족·옛 revision | ADR 작성(현재 `task_id`/`revision`, `status: ACCEPTED`, 보호 변경 전부를 scope 에) → DRAFT 에서 `attach` → `prepare` |

## Clarification

| 문자열 | 원인 | 복구 |
|---|---|---|
| `planning analysis must cover each required area exactly once` / `planning analysis incomplete: <area>` | 분석 area 누락·중복 | 모든 area 를 한 번씩 기록 |
| `unresolved material clarification <id>: <question>` | material 질문 미해결 | 사용자에게 그 질문을 묻고 답을 기록. 추측으로 채우지 않는다 |
| `planning record task/revision is stale; retain answers and reanalyze this revision` | `revise` 후 기록이 옛 revision | 답은 유지하고 `revision` 갱신 + 재분석 |
| `planning source excerpt no longer matches: <ref>` | 인용한 문서가 바뀜 | 현재 문서에서 excerpt 재인용, 의미가 바뀌었으면 재분석 |

## 검증 run / 증거

| 문자열 | 원인 | 복구 |
|---|---|---|
| `missing, disabled, or not enabled for profile` (`NOT_RUN`) | 선택된 check 가 config 에서 실행 불가 | check 를 enable/프로필 추가. config 변경이므로 `revise` 필요 |
| `source changed during verification` (check `source-stability`) | check 가 트리에 파일을 쓰거나 실행 중 편집 | 산출물을 `$PIPELINE_EVIDENCE_DIR` 또는 `generated_paths` 로 보내고, run 중 편집 금지 → 재실행 |
| `command left running descendant processes` | check 가 dev server/watch 를 남김 | 테스트 스크립트가 자식 프로세스를 직접 종료하도록 수정(watch 모드 금지) |
| `timeout` / `exit code N` | check 실패 | `logs/<id>.log` 를 읽고 **코드**를 고친 뒤 재실행. 같은 실패 3회 전에 접근을 바꾼다 |
| `Test evidence invalid: ...` (`Insufficient executed tests (zero/skip-only is not PASS)`, `Test skip allowance exceeded`, `Required test groups were not executed`) | test report 가 정책 미달 | 테스트를 실제로 실행·추가. skip 으로 통과시키지 않는다 |
| `frontend completion/Release requires screenshots/manifest.json` | frontend task 의 completion run 에 manifest 없음 | check 가 `$PIPELINE_EVIDENCE_DIR/screenshots/manifest.json` 에 `[{kind,path,width,height,url}]` 기록 |
| `both desktop and mobile screenshots are required` / `wrong declared <kind> screenshot dimensions` / `wrong decoded screenshot dimensions: ` | 크기·종류 불일치 | `desktop` 1440x900, `mobile` 390x844 (config `evidence`) 로 실제 PNG 캡처 |
| `Pillow is required to validate screenshot evidence` | 의존성 누락 | `python -m pip install -r requirements-pipeline.txt` |
| `run code snapshot is stale` / `run task/source fingerprint is stale` / `verification policy changed since run` | run 이후 코드·문서·config 가 변함 | 코드만 변했으면 completion 프로필 재실행. fingerprint/policy 면 `revise` |
| `Completion requires <expected> or Full evidence` / `Completion run is required` | `full_run` 이 없거나 잘못된 프로필 | `verification-plan --task <id>` 의 프로필 또는 `Full` 실행 |
| `acceptance criteria lack PASS evidence: ` / `acceptance criteria reference checks absent from evidence: ` | 기준의 check 가 run 에서 PASS 가 아님 | 해당 check 를 통과시키고 completion run 재실행 |
| `artifact integrity failure: <rel>` / `check log is not hash-bound` | `Reports/Pipeline/<run>` 파일이 수정·삭제됨 | 증거는 복구 불가. 새 run 을 실행 |
| `policy gate failed: <errors>` | `secret-detection`/`dependency-policy` 등 실패 | 나열된 오류를 고친다. 예외는 사용자 `exception` 승인뿐 |

## Budget / loop

| 문자열 | 원인 | 복구 |
|---|---|---|
| `failed-attempt limit reached; use loop renew --task` / `iteration active-time limit reached; use loop renew --task` | task budget 소진 | **멈추고 사용자에게 보고.** 승인받으면 `python -m web_pipeline loop renew --task <id> --reason "<user words>" --extra-attempts N --extra-minutes M` |
| `queue step limit reached; use loop renew --queue --extra-attempts` / `queue active-time limit reached; use loop renew --queue --extra-minutes` | queue budget 소진(`PAUSED_LIMIT`) | 위와 같이 사용자 승인 후 `loop renew --queue ...` |
| `Interrupted verification reservation; inspect processes then loop renew --task to settle budget` | run 도중 프로세스가 죽음 | 남은 check 프로세스를 PID 로 확인·종료 → 사용자 승인 후 `loop renew --task` |
| `same-failure limit reached` / `external retry limit reached` | 동일 failure fingerprint 3회 / 외부 BLOCKED 2회 | `loop renew` 로 풀리지 않는다. 재시도 중단, 원인과 log 를 사용자에게 보고 |
| `Unfinished action; inspect status and recover explicitly` (`BUSY`) | 완료되지 않은 lease | 작업을 마쳤으면 `loop complete --token <t> --outcome <o> --decision <json>`, 세션이 끊겼으면 `loop status` 로 token·프로세스 확인 후 `loop recover --token <t> --reason "<inspection notes>"` → `loop retry --task <id> --reason "<what changed>"` |
| `Task state changed during action; recover explicitly` / `Task revision changed...` / `Task scope changed...` | lease 중 수동 `run`/`transition`/`revise`/문서 편집 | `loop recover` → `loop retry`. lease 중에는 코드만 편집한다 |
| `Review changed source; do not approve unverified changes` | REVIEW action 중 트리가 변함(outcome 과 무관하게 거부) | 리뷰 중 만든 편집을 되돌린 뒤 `--outcome changes_required` 로 complete → 수정은 이어지는 `REPAIR` action 에서 |
| `Revision differs from authorized queue; scope must be reconciled explicitly` | queue 시작 후 `revise` | `loop reconcile --task <id> --reason "<why>"` (`revise` 로 만든 DRAFT revision 이어야 함) |
| `Queue already exists; resume it, or use loop renew...; never reset history` | `loop start` 중복 | `loop next` 로 이어간다. `AUTOPILOT.json` 삭제 금지 |
| `Baseline did not establish valid pre-change evidence` | Baseline 이 검증 불가(예: `NOT_RUN`/`BLOCKED`) | summary 의 원인을 고치고 `loop retry` |

## Review / approval

| 문자열 | 원인 | 복구 |
|---|---|---|
| `Current local review required: review --task <id> --decision <JSON>, or loop reviewed completion` | standard T1/T2 의 self-review 없음 | diff 와 completion report 를 검토 → `python -m web_pipeline review --task <id> --decision <file>` |
| `Local review is stale; review the verified source and completion report` | review 후 코드/run 변경 | completion run 재실행 → 다시 `review` |
| `missing valid <phase> approval for exact role <role> ...` | 필요한 승인 없음·stale | `python -m web_pipeline approval-request --task <id> --phase <phase>` → `request` 를 사용자에게 제시 → 동의 원문으로 `approve --task <id> --record <file>` |
| `Stale or mismatched approval request: <key>` / `User approval fingerprint is stale` / `User approval does not bind the completion summary bytes` | 레코드가 현재 request 와 다름 | `approval-request` 재실행, 새 값으로 레코드 작성, 사용자에게 다시 확인 |
| `Design approval must precede implementation` | IN_PROGRESS 이후 design 승인 시도 | design 승인은 `DRAFT`/`READY`/`BLOCKED` 에서만 기록된다. `revise` → `prepare` → design 승인 → 진행 |
| `Strict policy requires signed approvals; user receipts are not accepted` / `an external trust file is required (--trust or WEB_PIPELINE_TRUST)` | strict policy | 사람 승인자의 서명 레코드 + 프로젝트 외부 trust 파일. 에이전트가 키를 만들지 않는다 |

## init / upgrade / archive

| 문자열 | 원인 | 복구 |
|---|---|---|
| `init would overwrite existing files: <list>` | 대상에 동명 파일 존재 | `init --target <dir> --preview` 의 `conflicts` 확인 → 사용자와 상의해 이동/병합. 덮어쓰지 않는다 |
| `Locally modified/missing managed files: <list>` | 영수증에 기록된 엔진 파일(`web_pipeline/`, `Schemas/`, `Scripts/`의 엔진 파일)을 수정·삭제함. `Scripts/` 에 프로젝트가 **추가한** 파일은 `project_owned` 로 보존되어 해당 없음 | `git checkout -- <file>` 로 원복 후 `upgrade`. 엔진 수정은 kit 에서 |
| `Project files collide with new engine files; rename them first: <list>` | 프로젝트가 `Scripts/` 에 추가한 파일이 새 엔진 파일과 같은 이름 | 프로젝트 파일 이름을 바꾼 뒤 `upgrade` |
| `Legacy install requires --baseline with its known original engine directory` | `.pipeline-install.json` 없는 설치 | `upgrade --target <dir> --baseline <original-kit-dir>` |
| `Only compatible 2.6+ upgrades supported; no downgrade or implicit migration` | 2.6 미만이거나 downgrade | 지원 안 됨. 사용자에게 보고 |
| `Stop active pipeline operations before maintenance: <names>` | `upgrade`/`restore` 중 살아 있는 프로세스의 lock 존재(죽은 락은 자동 정리됨) | `locks` 로 PID 확인 → 그 작업이 끝날 때까지 대기 |
| `Unfinished upgrade requires restore: <txn>` / `Project changed during upgrade; restore transaction <txn>` | 중단된 upgrade | `python -m web_pipeline restore --target <dir> --transaction <txn>` |
| `only a DONE task can be archived: ` / `Phase evidence must be archived together: archive --task <phase> --include-members` | 대상 오류 | 메시지의 명령 그대로 |
| `Refusing to archive a potential local credential file: <rel>; isolate credentials before verification` | 트리에 `.env*`, `*.pem`, `*.key` 등(ignore 여부 무관) | 파일을 프로젝트 밖으로 옮김 → tree digest 가 변하므로 completion run 부터 다시 |

## Windows

- **CRLF**: tree digest 와 증거는 바이트 해시다. checkout 마다 줄바꿈이 바뀌면 `run code snapshot is stale` 가 난다 → `git config core.autocrlf false` + `.gitattributes` 에 `* text=auto eol=lf`.
- **BOM**: 엔진의 모든 JSON/텍스트 읽기(config, STATE.md, `ACCEPTANCE.json`, `CLARIFICATIONS.json`, `SCOPE.json`, ADR, `--plan`/`--decision`/`--record`)가 UTF-8 BOM 을 허용한다(2.11+). 다만 BOM 은 tree digest 에 포함되는 바이트이므로, 파일을 다시 저장하며 BOM 을 붙였다 뗐다 하면 fingerprint 가 stale 해진다 → 한 가지 방식(BOM 없음 권장)으로 통일.
- **명령**: `argv[0]` 는 PATH/PATHEXT 로 해석된다. `["npm","run","test"]` 그대로, `.cmd` 나 `cmd /c` 불필요(후자는 금지).
- **프로세스**: image name 으로 죽이지 않는다(`taskkill /IM node.exe` 금지). `python -m web_pipeline locks` 또는 log 에서 PID 확인 → `taskkill /PID <pid> /T`.
- 경로의 junction(`mklink /J`)도 `Link paths are forbidden` 대상.

## What never to do to get unstuck

- `STATE.md` 의 status, run pointer, `iteration` 카운터, `AUTOPILOT.json` 을 손으로 편집
- 테스트/lint 규칙을 약화·삭제·skip 하거나 `min_tests`·`timeout_seconds` 를 통과용으로 조정
- 변경을 넣은 뒤 Baseline 재캡처, 또는 증거(`Reports/Pipeline/*`, `LOCAL_REVIEW-*`, `USER_APPROVAL-*`) 삭제·수정
- 사용자 지시 없이 `loop renew`, 사용자가 말하지 않은 동의로 `approve`
- `.pipeline-locks/*.lock` 을 PID 확인 없이 삭제, `ARCHIVE_PENDING.json`·`.pipeline-upgrades/` 삭제
- 막힌 task 를 지우고 같은 id 로 재생성, `web_pipeline/` 엔진 파일 수정
