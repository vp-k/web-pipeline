---
description: Lean workflow - build features in order with tests, run pre-commit checks, get one review and commit with the check table
argument-hint: "<feature to build> | [--profile Fast|Task|Full]"
---

# lean 기능 개발

요청: `$ARGUMENTS`

lean 규칙은 프로젝트의 `Docs/Runbooks/LEAN.md` 한 곳에만 있다. 그 파일을 읽고 순서대로 진행한다. 명령은 프로젝트 루트에서 `python -m web_pipeline <command>`로 실행한다.

1. `python -m web_pipeline status`로 `workflow`, 준비 상태, `last_check`, `commit_gate`를 본다. `tracked`면 `/web-pipeline:task`를 쓴다.
2. 프로젝트 전체를 만드는 요청이면 LEAN.md의 "A whole project" 절대로 기능 목록부터 만든다.
3. 기능마다 "Per feature" 절의 순서를 따른다.
4. check 출력은 "Reading the check output" 표대로 처리한다. 엔진이 스크립트로 찾은 사실이니 다시 찾지 않는다.
5. `commit_gate`가 `ready`이면 리뷰를 `pipeline-reviewer` 에이전트에 맡긴다. 넘길 항목은 "Per feature" 절 5단계에 있다.

보고는 완성한 기능과 check 결과로 한다.
