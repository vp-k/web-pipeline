---
description: Read-only pipeline status - readiness, tasks, locks, queue and the next sensible command
argument-hint: "[TaskId]"
---

# 파이프라인 상태 (읽기 전용)

프로젝트 루트에서 실행한다. 인자가 있으면 `--task $ARGUMENTS`를 붙인다.

```console
python -m web_pipeline status
```

- `pipeline.config.yaml`이 없으면 도입되지 않은 저장소다. `python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" inspect --target .` 결과를 보여주고 `/web-pipeline:adopt`를 안내한다.
- 출력의 `next` 힌트, `locks`의 `alive: false` 항목(죽은 프로세스의 락 → `python -m web_pipeline locks --clear-stale`), `BLOCKED`/`DRAFT`로 되돌아간 작업의 이유를 요약한다.
- 특정 작업의 게이트 상세가 필요하면 `python -m web_pipeline validate --task <id>`, 큐는 `python -m web_pipeline loop status`.

이 명령은 **조회만** 한다. 수정, 상태 전이, 새 검증 실행, 아카이브를 하지 않는다. 용어가 낯설면 `references/glossary.md`.
