# 큐로 계속 개발하기 (`loop`)

사용자가 "계속 개발해", "끝날 때까지 반복해", 또는 기존 큐 재개를 요청했을 때 쓴다. 단발성 리뷰·상태 요청을 구현으로 바꾸지 않는다. 엔진 동작의 세부는 프로젝트의 `Docs/Runbooks/CONTINUOUS.md`.

## 큐 만들기 또는 재개

- `Docs/Work/AUTOPILOT.json`이 이미 있으면 `python -m web_pipeline loop status`로 확인하고 **재개**한다. 새로 시작하지 않는다.
- 범위 안의 DRAFT 작업과 문서를 만든다. 없는 기능을 지어내지 않는다.
- 새로 도입한 프로젝트의 첫 구현은 [adoption.md](adoption.md)의 "첫 기능을 끝까지"를 먼저 따른다. 첫 기능과 선행 작업만 큐에 넣거나, 이후 기능이 첫 기능의 Phase/작업에 `depends_on`하도록 한다.

계획 파일은 `Docs/Work/` 아래에 둔다:

```json
{
  "objective": "합의된 프로필 기능과 테스트 완료",
  "max_steps": 100,
  "elapsed_minutes": 120,
  "tasks": [
    {"task_id": "WEB-101", "depends_on": []},
    {"task_id": "WEB-102", "depends_on": ["WEB-101"]}
  ]
}
```

- 빈 `depends_on`은 "독립적으로 스케줄 가능"이라는 뜻이지, 공유 코드 변경의 영향을 받지 않는다는 뜻이 아니다.
- 의존성은 상태 문자열이 아니라 **현재 유효한 DONE**(필요한 승인 포함)을 요구한다. 진행하려고 의존성을 빼지 않는다.
- 프론트·백엔드가 함께 있어야 테스트가 되는 작업은 `implementation_groups`를 쓴다(`Docs/Runbooks/IMPLEMENTATION_GROUPS.md`): 계약·범위 정의 → 모든 멤버와 Phase `prepare` → 모든 멤버 Baseline·진입 게이트 → 그룹 `order`대로 백엔드, 프론트 구현 → 멤버별 Fast/Task/리뷰 → Phase 검증·리뷰. 그룹 내부의 `depends_on`은 거부된다.

```console
python -m web_pipeline loop start --plan Docs/Work/loop-plan.json
python -m web_pipeline loop next
```

워커 라벨 기본값 `claude`는 실행 라벨이지 사람이 아니다. `--trust`는 strict이거나 기존 서명 기록이 있을 때만 준다.

## 반복 절차

1. `loop next` — 정당한 전이와 실제 Baseline/Fast, 설정된 Task/Phase/Full 검증을 에이전트 작업이 필요해질 때까지 진행한다.
2. `ACTION_REQUIRED`면 작업, 현재 증거, 액션을 확인한다.

   | 액션 | 할 일 | 완료 outcome |
   | --- | --- | --- |
   | `PLAN` | 문서·계약·수용 기준 매핑·등급에 필요한 ADR 초안 작성 후 CLI로 `prepare`. Baseline 전에 제품 코드를 바꾸지 않는다 | `prepared` |
   | `IMPLEMENT` | 준비된 범위만 구현 | `implemented` |
   | `REPAIR` | `loop status`의 최신 실패 리포트·리뷰 결정을 읽고 가설을 세워 고친다. 테스트와 범위를 보존한다. 같은 명령을 그냥 다시 돌리지 않는다 | `implemented` |
   | `REVIEW` | 소스를 고치지 않고 코드·수용 기준·완료 증거를 검토한다. `pipeline-reviewer` 서브에이전트에 맡기고 결과를 옮겨 적는다 | `reviewed` 또는 `changes_required` |

   진행할 수 없으면 정직한 사유와 함께 `blocked`.
3. 결정 JSON을 **그 작업의 `Docs/Work/<TaskId>/` 안에** 쓴다. 필수 필드: `choice`, `rationale`, `alternatives`(실제로 고려한 대안 1개 이상), `risks`. 의미 있는 대안이 없으면 지어내지 말고 왜 없는지 쓴다. 자격 증명·개인정보를 넣지 않는다.
4. `python -m web_pipeline loop complete --token <token> --outcome implemented --decision Docs/Work/WEB-101/decision-001.json`
   outcome은 작업을 PASS나 DONE으로 만들지 않는다. 엔진이 선행 조건을 검증한다.
5. `CONTINUE`면 **턴을 끝내거나 계속할지 묻지 말고** 바로 `loop next`. 짧은 진행 보고만 남긴다. 실패 수리, 리뷰 재작업, 다음 작업 선택은 모두 같은 요청의 일부다.

standard의 보호되지 않은 T1/T2에서 `reviewed`는 소스에 묶인 로컬 리뷰를 남겨 로컬 리뷰 게이트를 충족한다. 이는 자기 리뷰·자문 증거이며 독립된 사람 승인이 아니다. 보호 변경·T3/T4는 별도의 사용자 영수증(standard) 또는 서명(strict)이 필요하다 → [approvals.md](approvals.md).

## 실제 정지 조건

| 결과 | 의미 | 할 일 |
| --- | --- | --- |
| `COMPLETE` | 큐의 모든 리비전이 현재 유효한 DONE 증거와 승인을 갖췄다 | 보고한다. 큐 완료는 배포도 머지도 하지 않는다. 기본 `completion_gate: "queue"`에서 merge_gate는 `NOT_APPLICABLE`(PASS 아님). 머지 준비 확인을 명시적으로 요청받았을 때만 `"merge"` |
| `WAITING` | 안전하게 진행할 작업이 없다 | 빠진 승인·의존성·낡은 범위/증거·외부 차단 요인과 다음 결정을 각각 보고한다. 변한 것이 없는데 `next`를 반복 호출하지 않는다 |
| `PAUSED_LIMIT` | 큐 또는 작업 예산 소진 | 두 한도를 모두 보고하고 **멈춘다**. 아래 "예산" 참고 |
| `BUSY` | 끝나지 않은 액션이 큐를 점유 | 두 번째 워커를 돌리지 않는다. 아래 "복구" 참고 |
| Git 통합 미완료 | 머지·리베이스 등이 진행 중이거나 실패 | 이 체크아웃의 작업을 모두 멈춘다. 오류와 변경을 보존하고, 작업을 마치거나 확인 후 명시적으로 중단한다. 실패를 건너뛰거나 큐를 새로 만들지 않는다 |

사용자의 명시적 중지, 권한 철회, 호스트 실행 불가도 정지 조건이다.

- 승인이나 외부 조건이 충족되면 확인한 뒤 `loop retry --task <TaskId> --reason "..."` 후 `next`. retry는 카운터를 초기화하지 않는다.
- 사용자가 범위를 바꾸면 `revise` 후 `loop reconcile --task <TaskId> --reason "..."`. 큐의 리비전을 몰래 바꾸지 않는다.
- 다른 작업이 공유 소스를 바꾸면 이전 REVIEW/DONE 증거가 낡을 수 있다. 큐는 닫힌 쪽으로 실패한다. 옛 승인을 재사용하지 말고 재검증한다.

## 복구 (`BUSY`, 세션이 죽은 뒤)

리스는 실행 전에 기록되고, 자동 만료나 맹목적 재실행은 없다. 작업 상태, diff, 실행 중인 프로세스, 증거를 확인하고 다른 워커·프로세스가 없음을 확인한 뒤:

```console
python -m web_pipeline loop recover --token <token> --reason "확인한 내용"
```

복구는 작업을 되돌리거나 다시 실행하지 않고 예산도 초기화하지 않는다. 호스트가 리스를 잡은 채 종료됐다면 그 구간 전체가 사용 시간으로 계산된다. 평소에 세션을 떠날 때는 액션을 `blocked`로 완료해 둔다.

`holds lock` 오류는 `python -m web_pipeline locks`로 확인한다. 프로세스가 죽은 락은 다음 실행 때 자동으로 회수된다. 살아 있는 프로세스의 락은 지우지 않는다.

## 예산 (`loop renew`)

큐의 활성 시간·스텝과 작업별 실패 시도·시간 예산은 별개다. **스스로 renew하지 않는다.** 사용자가 재개를 새로 요청했을 때, 소진된 예산만, 요청 한 번에 한 번만 늘린다. 수량을 지정하지 않았다면 기본 크기 1회(120분, 작업은 실패 시도 5회 / 큐는 100스텝)가 허용되는 해석이며, 늘린 양을 사용자에게 말한다. 예전의 포괄적 "계속해"는 무제한 renew 허가가 아니다.

```console
python -m web_pipeline loop renew --queue --reason "사용자가 기존 큐 재개를 요청" --extra-minutes 120
python -m web_pipeline loop renew --task WEB-101 --reason "사용자가 추가 시도를 요청" --extra-attempts 5
python -m web_pipeline loop next
```

- 대상은 정확히 하나(`--queue` 또는 `--task`), 양수의 분·시도, 실질적인 사유. `--trust`는 받지 않는다. 큐의 `--extra-attempts`는 스케줄링 스텝이다.
- 시간만 소진됐는데 시도 횟수를 늘리지 않는다. 응답의 `remaining_limit`을 확인한다.
- 열린 리스는 먼저 완료하거나 복구해야 한다.
- 초기 한도를 고치거나, 큐를 지우거나, 작업을 새로 만들어 사용량을 초기화하지 않는다. 승인·동일 실패·외부 재시도·낡은 증거 게이트는 renew 후에도 그대로다.

큐 체크포인트는 세션을 넘어 재개할 수 있지만, 이 플러그인은 데몬이 아니다. 종료된 Claude Code 세션을 깨우지 못한다. 무인 24/7 운영이라고 말하지 않는다.
