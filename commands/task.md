---
description: Run one tracked pipeline task end to end (classify, prepare, baseline, implement, verify, review, done)
argument-hint: "<what to build or fix> | <existing TaskId>"
---

# 추적 작업 1건 수행

요청: `$ARGUMENTS`

`web-pipeline` 스킬을 불러오고 `references/commands.md`의 최소 명령 순서를 따른다. 모든 명령은 프로젝트 루트에서 `python -m web_pipeline <command>`로 실행한다 (플러그인에 든 엔진이 아니라 **프로젝트 로컬 엔진**).

1. `python -m web_pipeline status` — 준비 상태, 진행 중인 작업, 잡힌 락을 먼저 본다. 인자가 기존 TaskId면 그 작업을 이어서 하고, 새로 만들지 않는다.
2. **질문은 계획 단계에서 한 번에** — 기존 코드·문서로 답이 정해지지 않는 범위/동작/데이터/수용 기준만 묶어서 묻고, 실제 답을 받은 뒤 진행한다. 침묵이나 에이전트의 제안은 답이 아니다. `CLARIFICATIONS.json`에 기록한다.
3. `new` → 문서 작성(`BRIEF.md`, `ACCEPTANCE.json`, 필요 시 `PLAN.md`/`SCOPE.json`) → `prepare` → `run --profile Baseline` → `transition --status READY`. 변경 **전에** Baseline을 잡는다. 변경 후 Baseline을 다시 잡아 사전 증거로 쓰지 않는다.
4. 구현 → `run --profile Fast` 반복 → `verification-plan --task <id>`가 가리키는 완료 프로파일(Task/Phase/Full) 실행.
5. **리뷰** — T1/T2는 `pipeline-reviewer` 서브에이전트에 diff와 수용 기준을 넘겨 새 컨텍스트에서 검토시킨 뒤, 그 결과를 `review --decision`으로 기록한다. 이것은 로컬 리뷰 기록이지 사람의 승인이 아니다.
6. 보호 변경·T3/T4·예외·Release는 `approval-request`로 필요한 결정을 확인하고, `NO_APPROVAL_REQUIRED`/`SATISFIED`가 아니면 해당 단계에서 필요한 결정을 **한 번에 묶어** 사용자에게 묻는다. `references/approvals.md` 참고.
7. `transition --status DONE` 후 작업 ID/리비전, 실제 상태, 실행된 check와 결과, 증거 경로, 실패와 남은 승인을 보고한다.

금지: STATE.md의 상태·카운터 수기 편집, PASS를 얻기 위한 테스트 약화/삭제/범위 축소, 위험 등급 하향, 승인·리뷰·로그 위조, 요청 없는 배포·운영 데이터 변경.
