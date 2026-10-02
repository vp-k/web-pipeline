---
description: Read-only pipeline status - readiness, tasks, locks, queue and the next sensible command
argument-hint: "[TaskId]"
---

# 파이프라인 상태 (읽기 전용)

프로젝트 루트에서 실행한다. 인자가 있으면 `--task $ARGUMENTS`를 붙인다.

```console
python -m web_pipeline status
```

- `workflow`를 먼저 알린다. `lean`이면 기능 작업은 `/web-pipeline:check` 흐름이고, `tracked`면 `/web-pipeline:task` 흐름이다.
- `missing_checks`는 지원 도메인이 요구하지만 켜지지 않은 check다. lean은 이 상태로도 진행하고 check 표에 남긴다.
- `ready_error`는 지금 설정으로 명령이 실패하는 이유다. `tracked`에서 필수 check가 꺼져 있으면 여기에 나온다. `next`가 고칠 방법을 알려준다.
- `pipeline.config.yaml`이 없으면 도입되지 않은 저장소다. `python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" inspect --target .` 결과를 보여주고 `/web-pipeline:adopt`를 안내한다.
- 출력의 `next` 힌트, `locks`의 `alive: false` 항목(죽은 프로세스의 락 → `python -m web_pipeline locks --clear-stale`), `BLOCKED`/`DRAFT`로 되돌아간 작업의 이유를 요약한다.
- 특정 작업의 게이트 상세가 필요하면 `python -m web_pipeline validate --task <id>`, 큐는 `python -m web_pipeline loop status`.

이 명령은 **조회만** 한다. 수정, 상태 전이, 새 검증 실행, 아카이브를 하지 않는다. 용어가 낯설면 `references/glossary.md`.
