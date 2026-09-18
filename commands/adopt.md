---
description: Adopt the web pipeline into a repository without overwriting anything, then wire real checks until the project is ready
argument-hint: "[target-path] [--domains frontend,api,...] [--ci]"
---

# 파이프라인 도입

대상: `$ARGUMENTS` (경로가 없으면 현재 작업 디렉터리). 도입은 **기능을 복사할 뿐**이며 프로젝트 준비 완료나 배포 권한을 뜻하지 않는다.

먼저 `web-pipeline` 스킬의 `references/adoption.md`와 `references/config-cookbook.md`를 읽는다.

## 순서

1. **점검** — 쓰기 전에 반드시 확인한다.
   ```console
   python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" doctor
   python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" inspect --target "<target>"
   python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" adopt --target "<target>" --preview
   ```
   - `doctor`가 `BLOCKED`면 빠진 의존성을 보고하고 멈춘다. 전역 `pip install`을 임의로 하지 않는다 (프로젝트 venv에 `requirements-pipeline.txt` 설치를 제안).
   - 이미 도입된 저장소(`adopted: true`)면 도입을 다시 하지 말고 `/web-pipeline:upgrade` 또는 `/web-pipeline:status`로 안내한다.
   - `--preview`의 `conflicts`가 비어 있지 않으면 멈추고 목록을 보여준다. 기존 파일을 지우거나 덮어써서 해결하지 않는다.
2. **스택 파악** — 저장소를 읽어 실제 구성요소(프런트/백엔드/DB/API), 패키지 매니저, 기존 테스트·린트·빌드 명령을 확인한다. 없는 백엔드를 만들어내지 않는다. 실제로 있는 도메인만 `--domains`로 넘긴다.
3. **도입** — `adopt --target "<target>" [--domains ...] [--ci]`. 결과의 `written`/`merged`/`preserved`를 사용자에게 그대로 보고한다.
4. **연결** — `pipeline.config.yaml`의 `sources`, `verification.commands`(실제 명령의 argv), `project.generated_paths`, 필요한 경우 `boundaries`/`verification.scopes`를 설정한다. 자리표시자 명령(`echo ok`, 항상 0을 반환하는 스크립트)을 연결하지 않는다.
5. **준비 확인** — Git 기준 커밋이 있는지 확인한 뒤 `project.ready: true`로 바꾸고 프로젝트 루트에서 `python -m web_pipeline validate`. 실패 문자열은 `references/troubleshooting.md`에서 찾는다.
6. **첫 기능 1개 검증** — 작은 T1 작업 하나를 DONE까지 끝내 검증 체인이 실제로 도는지 확인한 다음에야 나머지 작업으로 넓힌다.

## 보고

도입된 엔진 버전, 활성화한 check id와 각 명령, 비활성으로 남긴 check와 이유, `validate` 결과, 남은 사용자 결정 사항.
