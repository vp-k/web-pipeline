# 도입과 유지보수

플러그인을 설치했다고 현재 저장소에 파이프라인이 도입된 것은 아니다. 도입은 사용자가 요청했을 때만 한다.

## 도입 절차

1. **대상 확인.** 대상 저장소와 도입 의사를 확인한다. 기존 `CLAUDE.md`, Git 상태, 빌드·테스트 설정을 먼저 읽는다.
2. **점검.** `python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" doctor` — Python 3.11+, Git, `jsonschema`/`cryptography`/`Pillow`, 번들 해시 무결성을 본다. `BLOCKED`면 `missing`을 그대로 보고한다. 의존성 설치가 요청 범위라면 프로젝트 가상환경에 설치한다. 읽기 전용 감사 중에는 설치하지 않는다.
3. **미리보기.** `... pipeline.py inspect --target <절대경로>` 후 `... adopt --target <절대경로> --preview`. 둘 다 아무것도 쓰지 않는다. `can_adopt`, `conflicts`, `unsafe`, `preserved`, `merged`를 사용자에게 보여 준다.
4. **도입.** `... adopt --target <절대경로> [--domains frontend,backend,api] [--ci]`.

### 도입이 파일을 다루는 방식

| 구분 | 대상 | 동작 |
| --- | --- | --- |
| 엔진 (관리 대상) | `web_pipeline/`, `Schemas/`, `Scripts/`의 엔진 파일, `pipeline.config.yaml`, `PIPELINE.md`, `requirements-pipeline.txt` | 이미 있으면 **충돌 → 아무것도 쓰지 않고 중단** |
| 씨앗 문서 | `Docs/Governance·Runbooks·Product·Architecture·ADR`, `Templates/` | 없는 파일만 복사. 있는 파일은 `preserved`로 보고 |
| 병합 | `CLAUDE.md` | 끝에 `@PIPELINE.md` 임포트 블록 추가(없으면 생성). 기존 내용은 그대로 |
| 병합 | `.gitignore` | 없는 줄만 끝에 추가 |
| 복사 안 함 | README, `tests/`, `examples/`, `requirements.txt` | 프로젝트 것을 건드리지 않는다 |
| 선택 | `--ci` | `.github/workflows/project-policy.yml` |

- 충돌이 나면 사용자 파일을 지워서 통과시키지 않는다. 이미 도입된 프로젝트(`.pipeline-install.json` 존재)는 `upgrade`를 쓴다.
- `--domains`는 `project.supported_domains`를 줄인다. 백엔드가 없는 정적 사이트에 `database`·`payment` 요구사항을 억지로 채우지 않기 위한 것이다. 도메인 이름이 틀리면 `Unknown domain`으로 중단된다.
- 복사된 설정은 의도적으로 `mode: project`, `ready: false`다. 오류를 없애려고 `ready`를 켜지 않는다.

## 도입 후 설정

[config-cookbook.md](config-cookbook.md)의 스택별 레시피를 따른다. 핵심:

- 6개 소스 문서(`sources`), 지원 도메인, **실제로 실행해 본** argv 명령, 경로 규칙, Git 비교 기준(`base_ref`)을 채운다.
- 항상 통과하는 가짜 명령으로 실제 테스트를 대신하지 않는다. 테스트 0건, 비활성화된 필수 check는 커버리지가 아니다.
- 새 도입은 `approval_policy: standard`다. standard에서 사람 이름·신원·trust 파일을 요구하지 않는다. 보호 변경·T3/T4 결정은 사용자 영수증([approvals.md](approvals.md))으로 처리한다.
- 프론트/백엔드/API 경계가 있으면 설정 전에 프로젝트의 `Docs/Runbooks/BOUNDARIES.md`를 읽는다. 허용된 import와 금지된 import를 각각 한 번씩 실제로 검사해 어댑터가 동작함을 확인한다. `NOT_CONFIGURED`를 PASS로 보고하지 않는다.
- 순서: DRAFT 작업 생성 → 실제 명령 커버리지 확립 → 설정이 끝났을 때만 `ready: true` → `validate`. **프로젝트 준비(`ready`)와 작업의 READY는 다른 것이다.**

## 첫 기능을 끝까지, 그 다음에 확장

도입 요청에 구현이 포함될 때만 진행한다. 도입만 요청받았다면 설정과 실제 증거, 남은 일을 보고하고 끝낸다.

1. **저장소와 스택 매핑.** 런타임별 소스 루트·작업 디렉터리·허용 import·API 계약·검증 범위를 설정과 아키텍처 문서에 기록한다. 새 단일 저장소라면 사용자가 달리 정하지 않는 한 `backend/`, `frontend/`. DB 클라이언트와 자격 증명은 서버 쪽에만 둔다. 필요 없는 백엔드·DB를 만들지 않는다.
2. **실행 가능한 check 연결.** 빈 저장소라면 기능 구현 전에 최소 실행 스캐폴드와 실제 테스트 하네스만 만든다. 스캐폴드 수정 전에 가능한 Baseline을 실행하고, 없으면 사유와 함께 `NOT_RUN`으로 기록한다(PASS 아님). 각 명령을 선언된 cwd에서 실제로 돌려 본다.
3. **완결된 기능 하나 검증.** 요청 범위 안에서 실제 경계를 가로지르는 작은 기능을 고른다. UI 상호작용·API 응답·영속화·오류 경로의 관찰 가능한 수용 기준을 정한다. 프론트·백엔드가 연결된 작업은 멤버 작업 + Phase + `implementation_groups`를 쓴다([continuous.md](continuous.md)). mock만으로는 연결이 증명되지 않는다. 빌드 성공·doctor 통과·설정 검증은 기능 완료가 아니다.
4. **범위 안에서 확장.** 첫 기능의 완료 게이트가 통과한 뒤 나머지를 같은 체크아웃에서 이어 간다. 같은 계획에 이후 기능이 있으면 첫 기능의 Phase(또는 작업)에 `depends_on`을 건다.

이미 도입된 프로젝트를 재개할 때는 `python -m web_pipeline status`, 설정, 작업 STATE, 보존된 증거부터 확인한다. 유효한 증거는 재사용하고, 무관한 기능 때문에 위 순서를 처음부터 반복하지 않는다.

## 업그레이드

플러그인이 새 버전이 되어도 도입된 프로젝트의 엔진은 **자동으로 바뀌지 않는다**. 명시적 요청이 있을 때만:

1. `... pipeline.py upgrade --target <경로>` — 기본이 미리보기다. `changed`, `project_owned`, `preserved`를 보여 준다.
2. 사용자가 승인하면 `... upgrade --target <경로> --apply`. 관리 대상 엔진 바이트를 백업하고 교체하며, 반환된 `transaction` ID를 보고한다.
3. 프로젝트 로컬 엔진으로 `validate`와 새 검증을 돌린다. 업그레이드는 기존 준비 상태·승인·예산을 갱신하지 않는다.

규칙:

- `web_pipeline/`·`Schemas/` 안에서 파일이 수정·삭제·추가되어 있으면 `Locally modified/missing managed files`로 중단된다. 엔진을 프로젝트에서 직접 고치지 않는다.
- 프로젝트가 `Scripts/` 아래에 **추가한** 파일은 프로젝트 소유(`project_owned`)로 보존된다. 새 엔진 파일과 이름이 겹치면 `collide` 오류 — 프로젝트 파일 이름을 바꾼다.
- 업그레이드는 `pipeline.config.yaml`, `PIPELINE.md`, `Docs/`, `Templates/`, CI, 제품 코드, 증거를 건드리지 않는다. 적용 후 플러그인의 `kit/PIPELINE.md`·런북과 프로젝트 사본의 차이를 보여 주고, 반영 여부는 사용자가 정한다.
- 영수증(`.pipeline-install.json`)이 없는 옛 설치는 원본 엔진 디렉터리를 `--baseline`으로 줘야 한다. 현재 프로젝트에서 해시를 추측하지 않는다.
- 2.6 미만, 다운그레이드, 메이저가 다른 엔진은 거부된다. v1 등 호환되지 않는 파이프라인은 덮어쓰지 말고 명시적 마이그레이션 계획을 세운다(`Docs/Governance/MIGRATION_V1_TO_V2.md`).
- 살아 있는 프로세스가 잡은 락이 있으면 유지보수(`upgrade`·`restore`)가 거부된다. 죽은 프로세스의 락은 둘 다 자동 정리한다.

## 복원

`... pipeline.py restore --target <경로> --transaction <id>` — 해당 업그레이드 트랜잭션의 엔진 바이트만 되돌린다. 작업 상태·증거·예산은 초기화하지 않는다. `Unfinished upgrade requires restore: <id>`가 나오면 그 ID로 복원한 뒤 다시 시도한다.
