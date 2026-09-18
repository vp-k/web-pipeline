# web-pipeline 유지보수 규칙

이 저장소는 Claude Code 플러그인 `web-pipeline`이다. 프로젝트에 파이프라인이 **도입된 저장소가 아니다** — 여기서 `python -m web_pipeline`을 프로젝트 명령처럼 쓰지 않는다.

- 엔진 원본은 `kit/` 하나뿐이다. `kit/`을 바꾸면 `python tools/release.py`를 돌려 `kit-manifest.json`과 `plugin.json` 버전을 갱신한다. 안 하면 `doctor`와 `tests/test_distribution.py`가 실패한다.
- 버전은 `kit/web_pipeline/__init__.py`의 `__version__`에서만 올린다. 메이저 2 유지(엔진 업그레이드가 다른 메이저를 거부한다).
- 줄바꿈은 LF. 파일에 NUL 등 제어 문자를 넣지 않는다(해시·파싱 실패).
- 테스트: `python tools/test.py [이름…] [-j N]`. 전체 약 6분. 테스트는 `kit/`에서 복사해 임시 디렉터리에 도입하므로, 스위트가 도는 동안 `kit/`을 편집하지 않는다.
- 엔진 버그 수정은 `tests/`에 재현 테스트를 먼저 쓴다(unittest, 프레임워크 추가 없음).
- 정적 검사: `python -m ruff check kit scripts tools tests examples --select F,E9` 와 `python -m mypy kit/web_pipeline scripts tools --ignore-missing-imports` 가 0건이어야 한다.
- 사용자 대상 문서(`commands/`, `skills/`, README)는 한국어 본문 + 영어 frontmatter. `kit/` 안의 문서는 영어(프로젝트로 복사된다).
- `docs/history/`는 이전 Codex판 결정 기록이다. 배포되지 않고, 현재 동작의 근거로 인용하지 않는다.
- Windows 셸 호환을 유지한다. 프로세스를 죽일 때는 항상 PID로만.
