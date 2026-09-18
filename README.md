# web-pipeline

Claude Code 플러그인 **`web-pipeline`**: 웹 프로젝트에 위험 등급(T0–T4), 추적되는 작업(`Docs/Work/<TaskId>/`), 실제 검증 증거, 승인 게이트, 내구성 있는 작업 큐를 도입·운영하는 파이프라인 엔진과 그 운용 스킬.

- 엔진은 **프로젝트 안에 복사**된다(`python -m web_pipeline …`). 플러그인이 새 버전이 되어도 프로젝트의 엔진은 명시적 `upgrade` 전까지 바뀌지 않는다.
- 플러그인 자체는 도입·진단·업그레이드·복원만 담당한다(`scripts/pipeline.py`).

## 설치

```text
/plugin marketplace add vp-k/devncat
/plugin install web-pipeline@devncat
```

요구 사항: Python 3.11+, Git, 그리고 도입된 프로젝트에 `requirements-pipeline.txt`(`jsonschema`, `cryptography`, `Pillow`).

## 구성

| 항목 | 내용 |
| --- | --- |
| `/web-pipeline:adopt [path] [--domains a,b] [--ci]` | 프로젝트에 엔진 도입. 미리보기 → 충돌 없음 확인 → 복사. 기존 파일은 덮어쓰지 않는다 |
| `/web-pipeline:status [TaskId]` | 세션 시작 시 읽기 전용 현황(준비 상태, 작업, 락, 큐, 다음 할 일) |
| `/web-pipeline:task <TaskId>` | 작업 1건을 생성·준비·구현·검증·리뷰·완료까지 |
| `/web-pipeline:loop [plan]` | 큐로 여러 작업을 정지 조건까지 계속 |
| `/web-pipeline:upgrade [path] [--apply]` | 도입된 프로젝트의 엔진 업그레이드(백업·복원 포함) |
| 스킬 `web-pipeline` | 위 작업의 규칙·레퍼런스(`skills/web-pipeline/`). 요청에 따라 자동 로드 |
| 에이전트 `pipeline-reviewer` | 새 컨텍스트의 읽기 전용 리뷰어. T1/T2 로컬 리뷰 전에 사용 |

## 저장소 구조

```text
.claude-plugin/plugin.json   플러그인 매니페스트 (버전은 kit/web_pipeline/__init__.py에서 동기화)
commands/  agents/  skills/  Claude Code 구성 요소
kit/                         프로젝트로 복사되는 엔진·스키마·스크립트·문서 (유일한 원본)
kit-manifest.json            kit 파일 해시. doctor가 무결성 검사에 사용
scripts/pipeline.py          플러그인 부트스트랩 (doctor | adopt | inspect | upgrade | restore)
tests/                       엔진·배포 테스트 (python tools/test.py)
tools/release.py             버전 동기화 + 매니페스트 재생성
docs/history/                이전(Codex판) 결정 기록. 배포되지 않음
```

## 개발

```console
python tools/test.py                 # 전체 (파일 단위 병렬, 약 6분)
python tools/test.py friction cli    # 이름에 포함된 파일만
python tools/release.py              # kit 수정 후 반드시. 매니페스트·plugin.json 갱신
python tools/release.py --check      # CI/테스트가 쓰는 검사
python scripts/pipeline.py doctor
```

`kit/` 안의 파일을 바꿨다면 `python tools/release.py`를 돌려야 `doctor`와 `tests/test_distribution.py`가 통과한다. 버전은 `kit/web_pipeline/__init__.py`의 `__version__` 한 곳에서만 올린다(엔진 업그레이드 호환성 때문에 메이저는 2를 유지).

## Codex판에서 온 프로젝트

이전 `codex-web-pipeline`으로 도입한 프로젝트는 `/web-pipeline:upgrade`로 엔진만 올라간다. `PIPELINE.md`를 `kit/PIPELINE.md`에서 복사하고 `CLAUDE.md`에 `@PIPELINE.md` 한 줄을 추가하면 Claude Code가 같은 규칙을 읽는다. 기존 `AGENTS.md`는 그대로 둬도 된다.
