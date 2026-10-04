# E2E 시험 절차 (2.16.0)

이 문서는 배포되지 않는다. 2.16.0 엔진으로 웹 프로젝트 하나를 처음부터 끝까지 진행하는 절차다. 단계마다 실행할 명령과 확인할 출력을 적었다. 출력이 기대와 다르면 그 단계에서 멈추고 마지막 절의 기록표에 남긴다.

| 부분 | 확인하는 것 |
| --- | --- |
| A. lean 프로젝트 전체 | 기능 목록, Task check 범위, 기능 완료 조건, 커밋 |
| B. lean 안의 T4 작업 | tracked 전환, base_ref 기본값, 정책 변경, 완료 seal, Release |
| C. tracked 큐 | 커밋 시점, REPAIR 원인 |
| D. 완료 이후 | DONE 이력, revise 이월, archive 증거, merge gate |
| E. 2.15 업그레이드 | v1 fingerprint, `.gitattributes` |

용어:

- fingerprint: task 문서와 범위, 승인 규칙을 묶은 해시. 바뀌면 task 가 stale 이 되어 `revise` 가 필요하다.
- completion seal: DONE 전이 때 남기는 기록. 완료 당시의 문서, run, 승인 규칙을 묶는다. DONE 작업은 이 기록으로 판정한다.
- Task check: 바뀐 component 와 그것을 쓰는 component 의 check 만 도는 검사.

## 준비

- Git 저장소 하나와 첫 커밋.
- `frontend/`(브라우저), `backend/`(서버), `contracts/` 가 있는 웹 프로젝트. 각 쪽에 실제로 도는 테스트 명령이 있어야 한다.
- Python 3.11 이상과 `requirements-pipeline.txt` 설치.
- 플러그인 2.16.0 이 설치된 Claude Code 세션.

## A. lean 프로젝트 전체

### A1. 도입

```console
/web-pipeline:adopt . --domains frontend,backend,api
python -m web_pipeline status
```

확인:

- `workflow` 가 `lean` 이다.
- `.gitattributes` 에 `web_pipeline/**`, `Schemas/**`, `Docs/**`, `pipeline.config.yaml` 의 `eol=lf` 줄이 있다. 파일이 이미 있었다면 빠진 줄만 덧붙었다.
- `missing_checks` 에 아직 켜지 않은 필수 check 가 나온다.

### A2. check 와 scopes 설정

`pipeline.config.yaml` 에서 실제 명령을 켠다. `verification.scopes` 에 component `web`, `api` 를 둔다. 형태는 config-cookbook 의 (g) 구성을 따른다. lean 이므로 component `Phase` check 와 `phase_checks` 는 비워 둔다.

```console
python -m web_pipeline status
```

확인:

- `ready` 가 참이고 `ready_error` 가 없다.
- `phase_checks: []` 로 두어도 설정 오류가 없다.

설정을 커밋한다. 이 커밋이 이후 `check` 의 비교 기준이 된다.

### A3. 기능 목록

사용자에게 "이 프로젝트 전체를 만들어 줘" 라고 요청한다. Claude 가 기능을 만들 순서대로 넣는지 본다.

```console
python -m web_pipeline feature add "회원 가입과 이메일 형식 검증"
python -m web_pipeline feature add "프로필 조회와 수정"
python -m web_pipeline feature add "목록 화면과 페이지 나누기"
python -m web_pipeline feature list
python -m web_pipeline feature next
```

확인:

- ID 가 `F-001` 부터 차례로 붙는다.
- `feature next` 가 `F-001` 을 `ACTIVE` 로 바꾼다. 다시 부르면 같은 기능을 돌려준다.
- `status` 의 `features` 에 진행 중 기능과 다음 기능이 보인다.
- `Docs/Work` 아래에는 `FEATURES.json` 만 생긴다.

### A4. 기능 하나 만들기

순서대로 확인한다.

1. 구현 중에는 `check --profile Fast` 만 돈다.
2. 커밋 전에는 프로필 없이 `check` 를 돈다. scopes 가 있으므로 출력의 `profile` 이 `Task` 다.
3. `scope` 에 `level`, `components`, `reasons` 가 있다. `frontend/src` 만 바꿨다면 `web` 만 나온다.
4. `backend/src` 를 바꿨다면 `api` 와 그것에 의존하는 `web` 이 함께 나온다.
5. PASS 안내 끝에 "run check --profile Full before a release or merge" 가 붙는다.
6. `pipeline-reviewer` 리뷰가 한 번 있다.
7. `feature done` 이 성공하고 다음 기능을 안내한다.
8. 커밋 본문에 `commit_table` 이 있다. `FEATURES.json` 이 같은 커밋에 들어간다.

### A5. 범위 확장

각각 따로 바꿔 보고 되돌린다.

| 바꾼 것 | 기대하는 `scope` |
| --- | --- |
| `package.json` 또는 lock 파일 | `level: project`, 이유에 broad 경로 |
| `README.md` 처럼 어느 component 에도 없는 경로 | `level: project`, 이유에 소유자 없는 경로 |
| `pipeline.config.yaml` | `level: project`. `notices` 와 `weakened_checks` 도 확인 |

project 수준이면 실행되는 check 가 `check --profile Full` 과 같다.

### A6. 기능 완료 거부

| 상황 | 기대 |
| --- | --- |
| `feature next` 직후 check 없이 `feature done` | 거부. check 를 돌리라는 안내 |
| `check --profile Fast` 만 PASS | 거부. Fast 는 완료 근거가 아니다 |
| 마지막 Task check 가 FAIL | 거부. 고치고 다시 돌리라는 안내 |
| tracked 프로젝트에서 `feature add` | 거부. task 와 큐를 쓰라는 안내 |

### A7. 세션 이어 가기

기능 도중에 세션을 끝내고 새 세션을 연다.

- `status` 가 진행 중 기능을 보여 준다.
- `feature next` 가 새 기능을 시작하지 않고 진행 중 기능을 돌려준다.

### A8. 릴리스 전

모든 기능이 끝나면 `check --profile Full` 을 한 번 돈다. Task check 가 다루지 않은 component 까지 PASS 여야 한다.

## B. lean 안의 T4 작업

결제 기능을 하나 넣는다. 설정의 `supported_domains` 에 `payment` 가 있어야 한다.

### B1. check 가 tracked 를 요구

`backend/src/payment/` 아래를 바꾸고 `check` 를 돈다.

- `tracked_required` 가 참이고 `scope.level` 이 `project` 다.
- `feature done` 이 거부된다. T4 경로를 tracked task 로 옮기라는 안내가 나온다.

### B2. task 생성과 준비

```console
python -m web_pipeline new --task PAY-001 --title "Card checkout" --tier T4 --domains backend,api,payment --protected payment
python -m web_pipeline prepare --task PAY-001
```

확인:

- `--base-ref` 없이도 `new` 가 성공한다. STATE 의 `base_ref` 는 그 시점 HEAD 커밋이다.
- 개발에 필요한 check 가 꺼져 있으면 `prepare` 가 실패한다.
- Release 에만 필요한 check 가 꺼져 있으면 `prepare` 는 경고만 낸다.
- base_ref 가 비거나 틀린 DRAFT task 는 `prepare --task PAY-001 --base-ref HEAD` 로 고친다.

### B3. Baseline 부터 DONE 까지

Baseline, 구현, `run --profile Task` 순서로 간다. T4 이므로 Task 가 프로젝트 전체로 확장된다. 필요한 결정은 `approval-request` 로 보고 사용자에게 한 번에 묻는다. 답은 `approve` 로 기록한다.

정책 변경 시험:

| 바꾼 것 | 기대 |
| --- | --- |
| check 명령이나 프로필 같은 일반 설정 | fingerprint 그대로. 완료 run 은 "verification policy changed since run" 으로 거부되고 완료 프로필만 다시 돈다 |
| `payment` rule 의 `tier` 나 `roles`, 또는 `approval_policy` | fingerprint 가 바뀐다. `revise` 가 필요하다 |
| CLARIFICATIONS 가 인용한 문서 | fingerprint 가 바뀐다 |

DONE 전이 뒤 STATE 에 `completion_seal` 이 있는지 본다.

### B4. Release

`run --profile Release` 와 release 승인은 따로 거친다. 구현 완료가 Release 를 대신하지 않는다.

## C. tracked 큐

`workflow: tracked` 프로젝트를 하나 따로 도입한다. 작업 세 개짜리 계획으로 `loop start --plan` 을 부른다.

### C1. 커밋 방식 질문

- 큐를 시작할 때 한 번만 묻는다. 작업마다 커밋할지, 끝에 한 번 커밋할지다.
- 이후 같은 질문을 다시 하지 않는다.

### C2. commit_point

첫 작업이 DONE 이 되고 다음 작업이 구현을 시작하기 전에 `loop next` 를 부른다.

- 응답에 `commit_point` 가 있다. `tasks`, `revisions`, `message`, `instruction` 을 담는다.
- 작업마다 커밋을 골랐다면 Claude 가 `git status` 를 보고 그 메시지로 커밋한다.
- 같은 DONE revision 은 한 번만 제안된다. 이벤트 기록에 `COMMIT_POINT` 가 남는다.
- 다음 작업이 IMPLEMENT 를 시작한 뒤에는 제안이 없다.
- 커밋한 뒤에도 DONE 작업은 stale 이 되지 않는다.

### C3. REPAIR 원인

두 번째 작업에 일부러 실패하는 테스트를 넣는다.

- REPAIR 액션의 `required.repair` 에 실패 run 의 ID 와 프로필이 있다.
- 같은 곳에 실패 check 별 사유, 종료 코드, 로그 경로가 있다.
- 리뷰가 `changes_required` 로 끝났다면 `repair` 에 그 리뷰 결정이 있다.
- Claude 가 로그를 다시 뒤지지 않고 그 원인부터 고친다.

## D. 완료 이후

### D1. DONE 은 이력

B 의 PAY-001 이 DONE 인 상태에서 다른 기능을 계속 만든다. `pipeline.config.yaml` 의 일반 check 설정도 바꾼다.

- `status` 와 `validate --task PAY-001` 에서 PAY-001 이 stale 이 되지 않는다.
- `validate --gate merge` 는 여전히 엄격하다. 모든 작업을 현재 트리 기준으로 다시 본다. 통합 작업에는 현재 Phase run 이 필요하다.

### D2. revise 이월

tracked 작업 하나에서 CLARIFICATIONS 답과 ADR 을 만든다. 그 뒤 `revise --task <ID> --reason "<사유>"` 를 부른다.

- 새 revision 에 `CLARIFICATIONS.json` 과 ADR 이 그대로 있다.
- `REVISION_HISTORY` 에 `carried` 로 나온다.
- 이미 답한 질문을 사용자에게 다시 하지 않는다.

### D3. archive

```console
python -m web_pipeline archive --task PAY-001
```

- `Docs/Archive/PAY-001-r1/` 에 `EVIDENCE.zip` 이 있다.
- zip 에 Baseline, 완료, Release run 요약과 해시가 맞는 산출물, archive 시점 설정이 들어 있다.
- `ARCHIVE.json` 에 묶음 해시와 run 요약 해시가 있다.
- 다른 DONE 작업의 산출물 하나를 보고 디렉터리에서 바꾼다. 그 작업의 archive 는 거부된다.

## E. 2.15 프로젝트 업그레이드

2.15.x 로 도입해 tracked 작업을 하나 이상 만든 프로젝트를 쓴다.

```console
/web-pipeline:upgrade .
/web-pipeline:upgrade . --apply
```

- 기존 task 는 v1 fingerprint 를 유지한다. stale 이 되지 않고 seal 도 없다.
- 그 task 를 `revise` 하면 v2 fingerprint 가 된다.
- 업그레이드는 `.gitattributes` 를 건드리지 않는다. 안내대로 `gitattributes.txt` 의 빠진 줄을 사용자 동의 후 덧붙인다.
- lean 프로젝트는 `feature` 명령과 Task check 를 바로 쓴다.

## 기록표

기대와 다른 항목은 명령, 전체 출력, `git status` 를 함께 남긴다.

| 단계 | 결과 | 메모 |
| --- | --- | --- |
| A1 도입 | | |
| A2 설정 | | |
| A3 기능 목록 | | |
| A4 기능 하나 | | |
| A5 범위 확장 | | |
| A6 완료 거부 | | |
| A7 이어 가기 | | |
| A8 릴리스 전 Full | | |
| B1 tracked 요구 | | |
| B2 생성과 준비 | | |
| B3 DONE 과 정책 변경 | | |
| B4 Release | | |
| C1 커밋 방식 질문 | | |
| C2 commit_point | | |
| C3 REPAIR 원인 | | |
| D1 DONE 이력 | | |
| D2 revise 이월 | | |
| D3 archive | | |
| E 업그레이드 | | |
