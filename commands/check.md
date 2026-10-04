---
description: Lean workflow - build features in order with tests, run pre-commit checks, get one review and commit with the check table
argument-hint: "<feature to build> | [--profile Fast|Task|Full]"
---

# lean 기능 개발

요청: `$ARGUMENTS`

`web-pipeline` 스킬의 "작업 방식" 절과 프로젝트의 `Docs/Runbooks/LEAN.md`를 따른다. 명령은 프로젝트 루트에서 `python -m web_pipeline <command>`로 실행한다.

1. `python -m web_pipeline status`로 `workflow`와 준비 상태를 본다. `tracked`면 `/web-pipeline:task`를 쓴다.
   - lean은 실제 check가 하나라도 켜져 있으면 시작한다. 켜지지 않은 필수 check는 `missing_checks`로 나온다.
   - 켤 수 있는 check는 실제 `argv`로 켠다. 없는 도구를 있는 척하지 않는다.
2. 프로젝트 전체를 만들 때는 기능 목록을 먼저 만든다. 단일 기능 요청이면 이 단계를 건너뛴다.
   - `feature add "<기능>"`을 만들 순서대로 반복한다. 목록은 `Docs/Work/FEATURES.json`에 남는다.
   - `feature next`로 다음 기능을 시작한다. 이미 진행 중인 기능이 있으면 그 기능을 다시 알려 준다.
3. 기능 하나를 테스트와 함께 구현한다. 구현 중에는 `check --profile Fast`로 반복한다.
   - Fast는 도메인의 Fast 요구 check와 정책 check만 돈다. 프로젝트가 직접 정의한 check는 자기 `profiles`를 따른다.
4. 커밋 전에 `python -m web_pipeline check`를 돌린다. `FAIL`이면 원인을 고치고 다시 돌린다. 같은 원인으로 다시 돌리지 않는다.
   - `verification.scopes`에 컴포넌트가 있으면 기본은 Task다. 바뀐 컴포넌트와 그 소비자만 검사한다.
   - 넓은 입력, 주인 없는 경로, T4 변경은 프로젝트 전체 검사로 넓어진다. 결과의 `scope`가 범위와 이유를 보여 준다.
   - 컴포넌트가 없으면 기본은 Full이다. 릴리스나 병합 전에는 `check --profile Full`을 한 번 돌린다.
5. `decisions`가 있으면 이미 받은 답인지 확인한다. 아니면 한 번에 묶어 묻고 실제 답을 기다린다.
6. `weakened_checks`가 있으면 설정 변경이 검사를 줄인 것이다. 사용자가 그 축소를 결정했는지 확인한다.
7. `notices`는 결정이 아니라 리뷰가 확인할 항목이다. 의존성, `.env`, seed 데이터, 설정 변경이 여기에 나온다.
8. `tracked_required: true`면 멈추고 추적 task로 옮긴다고 보고한다.
9. `pipeline-reviewer` 에이전트로 기능 diff를 새 컨텍스트에서 리뷰한다. `notices`와 `weakened_checks`도 함께 넘긴다. 차단 지적은 고치고 check를 다시 돌린다.
10. 기능 목록을 쓰고 있으면 `feature done`으로 기능을 닫는다.
    - 기능 시작 뒤에 돈 마지막 Task 또는 Full check가 PASS여야 한다. Fast는 닫는 근거가 아니다.
    - 그 check가 추적 task를 요구했으면 닫히지 않는다. 그 작업을 추적 task로 옮긴다.
11. 커밋한다. 본문에 `commit_table`과 사용자 결정을 넣는다. 표의 `Not enabled` 줄은 지우지 않는다.
    - 기능 목록을 쓰면 `Docs/Work/FEATURES.json`도 같은 커밋에 넣는다. 그다음 `feature next`로 넘어간다.

일반 lean 작업은 `Docs/Work` 아래에 기능 목록만 둔다. task 폴더, 재개 메모, 실행 노트는 만들지 않는다. 기능 목록은 check 범위와 증거에 영향을 주지 않는다.

보고는 완성한 기능과 check 결과로 한다.
