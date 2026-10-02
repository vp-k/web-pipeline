---
description: Lean workflow - build one feature with tests, run pre-commit checks, get one review and commit with the check table
argument-hint: "<feature to build> | [--profile Fast]"
---

# lean 기능 개발

요청: `$ARGUMENTS`

`web-pipeline` 스킬의 "작업 방식" 절과 프로젝트의 `Docs/Runbooks/LEAN.md`를 따른다. 명령은 프로젝트 루트에서 `python -m web_pipeline <command>`로 실행한다.

1. `python -m web_pipeline status`로 `workflow`와 준비 상태를 본다. `tracked`면 `/web-pipeline:task`를 쓴다.
   - lean은 실제 check가 하나라도 켜져 있으면 시작한다. 켜지지 않은 필수 check는 `missing_checks`로 나온다.
   - 켤 수 있는 check는 실제 `argv`로 켠다. 없는 도구를 있는 척하지 않는다.
2. 기능 하나를 테스트와 함께 구현한다. 구현 중에는 `check --profile Fast`로 반복한다.
   - Fast는 도메인의 Fast 요구 check와 정책 check만 돈다. 프로젝트가 직접 정의한 check는 자기 `profiles`를 따른다.
3. 커밋 전에 `python -m web_pipeline check`를 돌린다. `FAIL`이면 원인을 고치고 다시 돌린다. 같은 원인으로 다시 돌리지 않는다.
4. `decisions`가 있으면 이미 받은 답인지 확인한다. 아니면 한 번에 묶어 묻고 실제 답을 기다린다.
5. `weakened_checks`가 있으면 설정 변경이 검사를 줄인 것이다. 사용자가 그 축소를 결정했는지 확인한다.
6. `notices`는 결정이 아니라 리뷰가 확인할 항목이다. 의존성, `.env`, seed 데이터, 설정 변경이 여기에 나온다.
7. `tracked_required: true`면 멈추고 추적 task로 옮긴다고 보고한다.
8. `pipeline-reviewer` 에이전트로 기능 diff를 새 컨텍스트에서 리뷰한다. `notices`와 `weakened_checks`도 함께 넘긴다. 차단 지적은 고치고 check를 다시 돌린다.
9. 커밋한다. 본문에 `commit_table`과 사용자 결정을 넣는다. 표의 `Not enabled` 줄은 지우지 않는다.

`Docs/Work` 폴더, 재개 메모, 실행 노트를 만들지 않는다. 보고는 완성한 기능과 check 결과로 한다.
