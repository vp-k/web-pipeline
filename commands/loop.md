---
description: Drive the durable work queue - keep acting on loop next until the queue is complete or a real stop condition is reached
argument-hint: "[queue plan path | resume]"
---

# 연속 개발 루프

큐는 추적 task를 다룬다. `workflow: lean` 프로젝트의 일반 기능 개발에는 쓰지 않는다.

인자: `$ARGUMENTS`. `web-pipeline` 스킬의 `references/continuous.md`와 `references/commands.md`(루프 절)를 읽는다.

```console
python -m web_pipeline loop status
python -m web_pipeline loop start --plan <plan.json>     # 큐가 없을 때만
python -m web_pipeline loop next
python -m web_pipeline loop complete --token <token> --outcome <outcome> --decision <decision.json>
```

## 규칙

- 큐를 시작할 때 사용자에게 한 번 묻는다. task마다 커밋할지, 끝에 한 번에 커밋할지다. 답은 큐가 끝날 때까지 쓴다.
- 응답에 `commit_point`가 있으면 DONE task만 작업 트리에 있는 시점이다. 사용자가 task별 커밋을 원했으면 `git status`를 보고 `message`로 커밋한다. 커밋은 task 증거를 바꾸지 않는다.
- `loop next`가 돌려준 **그 액션 하나**를 수행하고 `loop complete`로 닫은 뒤 다시 `loop next`. 중간 보고, 테스트 1회 통과, 참고용 리뷰는 멈출 이유가 아니다.
- `ACTION_REQUIRED`는 에이전트가 수행할 작업이다. `WAITING`/`FAIL`은 원인을 읽고 요청 범위 안의 수리·환경·기록 문제를 해결한 뒤 같은 큐를 재개한다. 실제 미해결 사용자 결정·외부 권한·강제 한도·사용자 중지에서만 멈춘다. `COMPLETE`면 결과를 보고한다.
- REPAIR 액션에는 `repair`가 붙는다. 실패한 실행의 check와 로그, 또는 변경을 요구한 리뷰 결정이 들어 있다. 그 원인부터 고친다.
- 루프의 단위는 기능이다. 구현하고 관련 검사로 확인한 뒤 다음 액션으로 간다. 절차 메모를 쓰는 데 턴을 쓰지 않는다.
- 같은 실패가 되풀이되면 엔진의 반복 한도가 멈춘다. 실패 시도 한도는 실패한 가장 넓은 프로필 이상의 PASS가 나오면 0으로 돌아간다. 테스트를 먼저 써서 한 번 실패하는 것은 한도를 소모하지 않는다. Full 실패 뒤의 Fast PASS는 그 실패를 지우지 않고, 같은 실패 반복 횟수도 끊지 않는다.
- 같은 실패나 외부 재시도 한도에 닿으면 원인과 log를 사용자에게 보고하고 멈춘다. 사용자가 원인을 밝혀 재개를 요청하면 그 사유로 `loop renew --task`를 한 번 한다.
- `time_budget_mode: warn`의 시간 경고는 정지나 renew 사유가 아니다. 개별 명령 timeout과 실패·반복·스텝 한도는 유지한다.
- `PAUSED_LIMIT`에서 스스로 `loop renew`하지 않는다. 사용자가 **새로** 재개를 요청하면 그 요청과 이유를 기록해 한 번, 한정된 양만 `renew`한다. 이전의 포괄적인 "계속해" 지시로 반복 갱신하지 않는다.
- 결정 JSON(`--decision`)은 저장소 작업 트리 밖이 아니라 해당 작업 폴더(`Docs/Work/<TaskId>/`)에 둔다. 작업 트리의 다른 곳에 쓰면 소스 지문이 바뀌어 증거가 무효가 된다.
- 리뷰 액션은 사용 가능한 `pipeline-reviewer`에 맡긴다. 기능이 없으면 별도의 로컬 검토를 수행하고 자체 리뷰임을 명시한다. 실제 결과를 `reviewed` 또는 `changes_required`로 기록한다.
- 실패한 큐를 버리고 새 큐로 갈아타거나 변경을 폐기해 우회하지 않는다. 막히면 `loop recover`/`retry`/`reconcile`의 용도를 `references/troubleshooting.md`에서 확인한다.
