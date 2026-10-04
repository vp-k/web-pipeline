# Changelog

## 2.16.0 — 프로젝트 전체를 끝까지

설치본으로 앱 하나를 처음부터 Release까지 진행해 본 결과를 반영했다.

버그 수정:

- `new`가 `--base-ref` 없이 현재 커밋을 기준으로 잡는다. DRAFT task는 `prepare --base-ref`로 기준을 정하거나 고친다. 이전에는 기준 없는 task를 버리고 새 ID로 다시 만들어야 했다.
- 도입이 `.gitattributes`에 엔진, 스키마, 문서, 설정의 LF 고정 줄을 넣는다. upgrade, restore, doctor는 CRLF로 받은 사본을 내용으로 비교한다. 실제 편집은 계속 막는다.
- `prepare`가 task에 필요한 개발 check가 꺼져 있으면 실패한다. T4에 필요한 Release check가 꺼져 있으면 경고한다. 이전에는 완료 직전 run에서야 `NOT_RUN`으로 드러났다.
- 큐의 REPAIR 액션이 `repair`로 원인을 준다. 실패한 run의 check별 사유, 종료 코드, 로그, 또는 수정을 요구한 리뷰 결정이다.
- `prepare`가 revise 사유를 `blockers`에서 지운다. 사유는 `REVISION_HISTORY`에 남는다.

설계 변경:

- lean 기능 목록을 추가했다. `feature add`, `list`, `next`, `done`이 `Docs/Work/FEATURES.json`에 순서와 진척을 남긴다. `feature done`은 기능 시작 뒤의 Task 또는 Full check PASS가 필요하다.
- lean `check`의 기본 프로필이 scopes가 있으면 `Task`다. 바뀐 component와 그 소비자의 check만 돈다. broad 경로, 소유자 없는 경로, T4는 Full과 같은 범위로 넓힌다. 결과에 `scope`가 붙는다.
- lean 프로젝트는 scopes의 `Phase` check와 `phase_checks`를 비워 둘 수 있다. tracked는 계속 필요하다.
- fingerprint v2: task 문서와 범위, 승인 규칙, CLARIFICATIONS가 인용한 문서, 경계 계약만 묶는다. 일반 설정 변경은 task를 stale로 만들지 않는다. 대신 완료 run을 다시 돌려야 한다.
- DONE은 이력이다. DONE 전이 때 completion seal을 남기고, 이후 프로젝트 변경은 DONE task를 다시 열지 않는다. merge gate는 그대로 엄격하다.
- `revise`가 CLARIFICATIONS와 ADR을 새 revision으로 옮기고 `carried`로 기록한다. 답한 질문과 결정을 다시 받지 않는다.
- 큐가 커밋 시점을 알린다. DONE task만 트리에 있고 다음 task가 구현을 시작하기 전이면 `loop next`가 `commit_point`를 준다.
- archive가 `EVIDENCE.zip`을 남긴다. run 요약, 해시를 확인한 산출물, 그 시점 설정이 들어간다.
- 2.16 전에 준비한 task는 revise 전까지 v1 fingerprint를 유지하고 seal이 없다. 업그레이드는 `.gitattributes`를 고치지 않는다. `UPDATES.md`를 따른다.

## 2.15.1 — 지침 정리

- `PIPELINE.md`의 증거 절이 엔진이 만들지도 읽지도 않는 `VERIFICATION.md`를 가리켰다. 수용 기준은 `ACCEPTANCE.json`의 check ID로 증명한다고 고쳤다. 쓰이지 않던 `Templates/VERIFICATION_TEMPLATE.md`는 지웠다. 이미 도입된 프로젝트의 사본은 업그레이드가 건드리지 않는다.
- 스킬 트리거에 lean 기능 작업과 커밋 전 check를 넣었다. 이전에는 tracked 작업만 지목해 새 도입 기본값인 lean 작업에서 스킬이 불리지 않았다.
- 스킬의 lean 규칙 8번을 `LEAN.md`와 맞췄다. 파괴적 마이그레이션, 의미상 T4, 감사 증거 요청도 추적 task를 쓴다.

## 2.15.0 — 기능 우선 검사

- lean 프로젝트는 실제 check가 하나라도 켜져 있으면 시작한다. 켜지지 않은 필수 check는 `status`와 `check`의 `missing_checks`, 결과표의 `Not enabled` 줄로 남는다. tracked는 기존 준비 조건을 유지한다.
- `status`가 설정 오류를 미리 보여 준다. `ready_error`에 명령이 실패할 이유가 나오고, tracked 프로젝트에는 lean 전환 방법을 안내한다.
- `check --profile Fast`가 도메인의 Fast 요구 check와 정책 check만 돌린다. 정책 check는 모든 lean 프로필에서 돈다.
- `check`가 `--base-ref`의 설정과 비교해 꺼지거나 빠진 check, 줄어든 요구, 빠진 보호 rule을 `weakened_checks`로 보고한다. 사용자 결정이 필요하다.
- path rule에 `match`(`word`/`name`/`path`/`glob`), 패턴 목록, `except`, `notice`를 추가했다. `match`가 없는 rule은 예전처럼 대소문자 구분 glob이다.
- 기본 rule을 단어 단위로 바꿨다. `useOAuth.ts`, `SignIn.tsx`는 인증으로 잡고 `AuthorCard.tsx`, `BlockList.tsx`는 잡지 않는다. `.sql`, `.prisma`, `.env` 류, 키 파일, Dockerfile, compose, 배포 설정도 해당 보호 변경으로 잡는다.
- 의존성 manifest와 lock 파일은 T3 결정 대신 T0 notice다. seed, `.env` 류, `pipeline.config.yaml` 변경도 notice로 리뷰가 확인한다. 엔진 파일은 계속 T3 `core_architecture`다.
- `.tsx`, `.jsx`, `.vue`, `.svelte`, `.astro`, 스타일 파일은 frontend, `app/api`·`pages/api`·`server` 경로와 `.go`·`.php`·`.rb`·`.java`·`.kt`는 backend 도메인을 받는다.
- `pipeline-reviewer`가 notice와 `weakened_checks`를 확인한다.

## 2.14.0 — lean 모드

- 설정에 `workflow`(`lean`/`tracked`)를 추가했다. 새 도입은 `lean`이다. 값이 없는 기존 프로젝트는 `tracked`로 동작이 바뀌지 않는다.
- `check` 명령을 추가했다. task 없이 작업 트리에서 활성 check를 돌리고 커밋 메시지용 결과표를 낸다. 실패하면 exit 1이다.
- `check`는 변경 경로를 분류해 사용자 결정이 필요한 보호 변경(`decisions`)과 T4 여부(`tracked_required`)를 알려 준다.
- lean 모드는 기능 단위로 구현하고, 커밋 전 check와 리뷰 1회를 거친다. `Docs/Work` 기록은 T4 작업에만 쓴다.
- `/web-pipeline:check` 명령, `LEAN.md` 런북, `status`의 `workflow` 표시와 안내, `adopt --workflow`를 추가했다.

## 2.13.0 — 기능 단위 검증

- T3·보호 변경이 더 이상 모든 검사를 프로젝트 전체로 확장하지 않는다. 바뀐 component 검사에 그 task 도메인과 보호 규칙의 필수 check를 더한다. Baseline은 도메인의 Baseline 요구, Task/Phase는 Full 요구를 쓴다.
- Fast는 위험 등급 때문에 확장하지 않는다. T4의 Baseline/Task/Phase는 계속 프로젝트 전체다. Full·Release와 broad path·모호한 경로의 확장은 그대로다.
- 지침에 작업 리듬을 추가했다. 기능 구현, 관련 검사, 다음 기능 순서다. 같은 원인으로 막힌 검증 반복과 엔진이 요구하지 않는 절차 메모를 금지한다.

## 2.12.1 — 진단 회귀 수정

- `loop status`/`loop next`가 설정 파일이 구조적으로 깨진 상태(JSON 문법 오류, 활성 명령의 `cwd` 부재 등)에서 예외로 끝나 활성 리스를 가리던 2.12.0 회귀를 고쳤다. 작업별 누적 시간 경고를 계산할 수 없으면 `Task time warnings unavailable: …` 경고만 남기고 BUSY/리스를 그대로 보여 준다. 실행(`loop complete` 등)은 여전히 정상 설정 검증에서 막힌다.

## 2.12.0 — 반복 중단 완화와 제품 중심 도입

- 일반 개발 준비에서 Release 전용 check 활성화를 요구하지 않는다. Release 실행 시 필수 검사·승인·NOT_RUN 판정은 유지한다.
- 새 도입은 누적 시간 `warn`, 기존 미지정 설정/큐는 `enforce` 유지. 명령별 timeout과 실패·반복·외부 재시도·스텝 한도는 유지한다. 순수 시간 중단은 실패 시도 예약만 환불하고 BLOCKED와 사용량을 보존한다.
- 승인 진단에 `CHECK_EXISTING_CONSENT`, 기획 진단에 `REPAIR_RECORD`/`CHECK_EXISTING_REQUIREMENTS`를 제공해 기록 문제를 새 사용자 질문으로 처리하지 않는다.
- 복구 가능한 실패·리스·Git 문제는 기존 요청 안에서 해결한다. 선택적 보관·리뷰 도구 부재·세션 전환이 반복 허락 질문을 만들지 않도록 지침을 통일했다. 보호 결정·예외·Release·운영 승인은 유지한다.
- 도입은 실제 도메인·기존 문서/명령을 재사용하고 요청된 첫 기능으로 검증한다. 도입 전용 요청의 시범 기능과 작은 연결 기능의 강제 task/Phase 분할을 없앴다.
- 기존 프로젝트의 엔진·설정·거버넌스는 자동으로 덮어쓰지 않는다. 상세 점검과 이행 기준은 `docs/FRICTION_AUDIT.md`.

## 2.11.0 — Claude Code plugin

첫 Claude Code 판. 엔진은 `codex-web-pipeline` 2.10.1에서 이어진다.

### 플러그인
- `.claude-plugin/plugin.json`, 명령 `adopt`/`status`/`task`/`loop`/`upgrade`, 스킬 `web-pipeline`(레퍼런스 9종), 에이전트 `pipeline-reviewer`.
- 부트스트랩 `scripts/pipeline.py`: `doctor | adopt | inspect | upgrade | restore`. 번들 해시(`kit-manifest.json`) 검증, 링크·플러그인 내부 대상 거부. 이전의 `project` 모드는 제거 — 프로젝트 안에서는 `python -m web_pipeline`만 쓴다.
- `tools/release.py`로 버전·매니페스트 단일화. `tools/test.py` 병렬 러너(30분 → 약 6분).

### 엔진 (실사용에서 확인된 마찰 수정)
- **Windows `.cmd` 심**: check 명령의 첫 인자를 PATH/PATHEXT로 해석해 `npm`, `pnpm`, `npx`가 셸 없이 실행된다(이전에는 `WinError 2`).
- **죽은 프로세스의 락**: 기록된 PID가 확실히 사라진 `.pipeline-locks/*.lock`은 다음 실행이 회수한다. 새 명령 `locks [--clear-stale]`. 오류 문구에 PID·시작 시각 포함.
- **UTF-8 BOM**: 엔진의 모든 JSON/텍스트 읽기가 BOM을 허용한다(PowerShell이 쓴 파일).
- **새 명령 `status [--task]`**: 도입 여부·준비 상태·작업·락·큐·다음 할 일. 미도입 디렉터리에서도 예외 없이 힌트를 준다.
- **도입(`init`)**: 엔진 파일만 충돌로 취급. `Docs/`·`Templates/`는 없는 파일만 복사, `CLAUDE.md`에 `@PIPELINE.md` 임포트 추가, `.gitignore`는 없는 줄만 추가, `requirements-pipeline.txt`로 분리. README·tests·examples는 복사하지 않는다. `--domains`, `--ci` 옵션.
- **업그레이드**: 프로젝트가 `Scripts/` 아래에 추가한 파일은 `project_owned`로 보존(충돌 시 `collide` 오류). 죽은 락은 유지보수를 막지 않는다.
- **`project.respect_gitignore`**(기본 `true`): git이 무시하는 추적되지 않은 파일(`.turbo/`, `*.tsbuildinfo` 등)을 소스 핑거프린트에서 제외.
- **경로 규칙**: `*lock*`(BlockList.tsx까지 T3로 올리던 규칙)을 실제 잠금 파일 패턴 7개로 교체.
- **`validate` 가 task 없이도 설정을 검사**: `no tasks found` 는 progress 게이트에서 경고(`--gate merge` 에서만 오류). 도입 직후 설정 검증이 가능해졌다.
- **`base_ref` 검증**: `-`로 시작하는 값(`--output=…` 등)은 `new`·`validate --base-ref`·diff 검사에서 git 에 닿기 전에 거부된다. git diff 호출에 120초 타임아웃.
- **CI 워크플로(`--ci`)**: 도입된 프로젝트에서는 `requirements-pipeline.txt`를 설치한다(있으면). 이전에는 프로젝트 자신의 `requirements.txt`를 설치하거나 실패했다.
- **`loop status` 는 항상 exit 0**: 읽기 전용 조회가 `BUSY`/`PAUSED_LIMIT`에서 1을 반환하지 않는다. `loop next` 등 액션의 exit 의미는 그대로.
- `status` 힌트 순서 수정(`ready=true` → `validate`; `validate`는 NOT_READY 프로젝트를 거부한다). `.gitignore` 시드에 `build/ .next/ coverage/ test-results/ playwright-report/` 추가(`generated_paths` 기본값과 일치).
- 리뷰 반영: `upgrade`·`restore`가 죽은 프로세스의 락을 실제로 회수한다(이전에는 회수한 락 이름을 그대로 차단 사유로 보고했고, `restore`는 아예 회수하지 않았다). `restore`는 미완료 업그레이드 검사를 하지 않는다(그것을 해결하는 명령이므로). `base_ref` 오류 문구를 `must be a git revision, not an option`으로 통일. `plugin.json`의 `skills`를 `./skills` 디렉터리로.
- 리뷰 반영: 설정에 `respect_gitignore` 키가 없는 이전 프로젝트도 기본값 `true`로 동작(이전엔 조용히 꺼짐). `ci.py`의 base_ref 검사를 `policy.option_shaped`로 통일. `scripts/pipeline.py`·`tools/release.py`도 BOM 허용. POSIX PATH 해석 테스트 추가.
- 사용하지 않던 코드 제거(`runner.FORBIDDEN_SHELL_FLAGS`/`SHELLS`, `scopes._closure`, 미사용 import). `ruff check --select F` · `mypy` 클린.
- 실행 라벨 기본값 `codex` → `claude`. `AGENTS.md`+`PLANS.md` → `PIPELINE.md` 하나로.
- 저장소 전체 LF 통일(`.gitattributes`), 문서에서 버전 서사·standard/strict 모순 정리.
