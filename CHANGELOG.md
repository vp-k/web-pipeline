# Changelog

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
