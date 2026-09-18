---
description: Preview and, only on explicit request, apply a managed engine upgrade for an adopted project (with backup and restore)
argument-hint: "[target-path] [--apply]"
---

# 엔진 업그레이드

대상: `$ARGUMENTS` (경로가 없으면 현재 디렉터리).

```console
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" inspect --target "<target>"
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" upgrade --target "<target>"
```

1. 기본은 **미리보기**(쓰기 없음)다. `changed`(바뀌는 관리 파일), `project_owned`(프로젝트가 `Scripts/` 아래에 추가한 파일 — 보존됨), 버전 전후를 보여준다.
2. 사용자가 이번 대화에서 명시적으로 업그레이드 적용을 요청한 경우에만 `--apply`. 일반 작업 도중 조용히 업그레이드하지 않는다.
3. 막히는 경우:
   - `Locally modified/missing managed files` — 관리 파일(`web_pipeline/`, `Schemas/`, `Scripts/`의 엔진 파일)을 프로젝트가 수정·삭제했거나 `web_pipeline/`·`Schemas/`에 파일을 추가했다. 목록을 보여주고 사용자가 되돌릴지 결정하게 한다. 임의로 덮어쓰지 않는다.
   - `Legacy install requires --baseline` — 영수증(`.pipeline-install.json`)이 없는 설치다. 원래 설치한 엔진 디렉터리를 **실제로 알고 있을 때만** `--baseline`으로 넘긴다. 기준선을 지어내지 않는다.
   - `Stop active pipeline operations before maintenance: <names>` — 살아 있는 프로세스가 락을 잡고 있다(죽은 프로세스의 락은 자동 정리된다). `python -m web_pipeline locks`로 PID를 확인하고 그 작업이 끝날 때까지 기다린다. 프로세스를 이미지 이름으로 죽이지 않는다.
   - `Project files collide with new engine files; rename them first` — 프로젝트가 `Scripts/`에 추가한 파일이 새 엔진 파일과 이름이 같다. 이름 변경은 사용자가 결정한다.
4. 적용 후: 거래 ID를 보고하고, `Docs/`·`Templates/`·`pipeline.config.yaml`·`PIPELINE.md`는 업그레이드가 건드리지 않으므로 플러그인 `kit/`의 최신본과 차이를 비교해 알려준다. 그 다음 `python -m web_pipeline validate`. 업그레이드는 기존 증거나 준비 상태를 갱신해 주지 않는다.
5. 되돌리기: `python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" restore --target "<target>" --transaction <id>`.
6. 이전 판(`AGENTS.md` 기반, 2.10 이하)에서 넘어온 프로젝트: 엔진 업그레이드 후 `PIPELINE.md`가 없으면 플러그인의 `kit/PIPELINE.md`를 복사하고 `CLAUDE.md`에 `@PIPELINE.md` 줄을 추가할지 사용자에게 제안한다. 기존 `AGENTS.md`는 지우지 않는다.
