# Quickstart: 도입부터 첫 DONE 까지

실제 저장소에 엔진을 도입하고 T1 task 하나를 DONE 으로 만드는 최단 경로. 명령 상세는 [commands.md](commands.md), 설정 레시피는 [config-cookbook.md](config-cookbook.md), 채워진 문서 예시는 [worked-example.md](worked-example.md).

## 0. 전제

- Python 3.11+, Git. 대상은 Git 저장소이고 commit 이 하나 이상 있어야 한다.
- 플러그인 점검: `python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" doctor` → `PASS`. `missing` 이 있으면 설치 후 다시 실행한다. 없는 도구를 있는 척하지 않는다.

## 1. 도입 (미리보기 먼저)

```console
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" adopt --target "<project>" --preview --domains frontend,backend
python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" adopt --target "<project>" --domains frontend,backend
```

- `--preview` 는 쓰지 않고 충돌만 보여 준다. 충돌이 있으면 사용자에게 보고한다. 도입은 기존 파일을 **덮어쓰지 않는다**.
- `--domains` 는 `project.supported_domains` 를 채운다. `--ci` 는 선택적 CI workflow 도 복사한다(사용자가 원할 때만).
- 프로젝트에 생기는 것: 엔진(`web_pipeline/`, `Schemas/`, `Scripts/`, `Templates/`, `Docs/`), `pipeline.config.yaml`(`mode: "project"`, `ready: false`), 에이전트 지침 `PIPELINE.md`, `CLAUDE.md` 의 `@PIPELINE.md` import, `.gitignore` 추가분, `requirements-pipeline.txt`.

의존성은 전역이 아니라 venv 에 설치하고, 이후 모든 엔진 명령은 그 venv 가 활성화된 셸의 프로젝트 루트에서 실행한다.

```console
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-pipeline.txt
```

(macOS/Linux: `.venv/bin/python -m pip install -r requirements-pipeline.txt`)

## 2. 설정 체크리스트 (`project.ready: true` 까지, 순서대로)

1. **sources**: `sources` 6개(`product_spec`, `feature_spec`, `api_contract`, `data_contract`, `security_policy`, `architecture`)가 실제로 존재하는 저장소 상대 경로여야 한다. 도입된 `Docs/` 템플릿을 프로젝트 내용으로 채우거나 기존 문서 경로로 바꾼다.
2. **supported_domains**: 이 저장소가 실제로 다루는 도메인만 남긴다. 도메인마다 필수 check 가 늘어난다.
3. **commands**: 도메인이 요구하는 check id 마다 실제 명령을 `argv` 배열로 배선하고 `enabled: true`. 배선 전에 각 명령을 그 `cwd` 에서 직접 실행해 동작을 확인한다. `policy_checks` 와 지원 도메인의 Baseline/Fast/Full/Release 목록에 있는 id 가 하나라도 disabled 면 모든 명령이 `Required project command <id> is disabled` 로 실패한다. 도구가 없는 check 는 더미로 채우지 말고 cookbook §3 절차로 목록을 조정한다.
4. **출력 경로**: `project.respect_gitignore: true` 이면 Git 이 무시하는 빌드 출력(`.next/`, `dist/`, `coverage/`)은 자동 제외된다. 아니면 `project.generated_paths` 에 루트 기준 경로로 적는다. 빠뜨리면 검증 run 이 `source changed during verification` 으로 FAIL 한다.
5. **path rules**: `risk.path_rules` 에 프로젝트의 실제 auth·migration·계약 위치와 `.ts`/`.py` 등 소스 rule 을 더한다(cookbook §6).
6. `project.name` 을 정하고 `"ready": true` 로 바꾼다.
7. **Git baseline commit**: 엔진·설정·문서를 모두 commit 한다. 첫 task 의 diff 에 `pipeline.config.yaml` 이나 엔진 파일이 섞이면 그 task 가 T3 로 승격되므로 task 생성 **전에** commit 한다.
8. **base_ref**: 이 baseline commit 이 첫 task 의 비교 기준이다. `new --base-ref HEAD` 는 그 시점의 commit 으로 고정된다.

`ready: true` 이후의 설정 변경은 T3 통제 변경이다. 설정은 이 단계에서 끝낸다.

## 3. 첫 task 와 validate

task 가 없어도 `validate` 는 설정을 검사한다(`no tasks found` 는 경고. `--gate merge` 에서만 오류). 설정이 `PASS` 인 것을 확인한 뒤 첫 task 를 만든다(`new` 는 `ready` 와 무관하게 동작한다).

```console
python -m web_pipeline validate
python -m web_pipeline new --task APP-001 --title "Show validation hint on name field" --tier T1 --domains frontend --base-ref HEAD
python -m web_pipeline status
```

- `validate` 는 `ready: false` 면 `Project is NOT_READY` 로 FAIL 하므로 2절을 끝낸 뒤 실행한다. `PASS`(exit 0)면 설정이 유효하다. FAIL 이면 오류를 고친다. 고치기 어려우면 `ready: false` 로 되돌리고 보고한다. `--kit` 은 프로젝트용 우회로가 아니다.
- `boundaries` 미설정 경고(`NOT_CONFIGURED`)는 오류가 아니다. import 격리가 증명되지 않았다는 뜻이다.
- `status` 는 읽기 전용 요약과 `next` 힌트를 준다. 세션을 시작하거나 재개할 때 항상 먼저 실행한다.

## 4. T1 task 를 DONE 까지

에이전트가 작성하는 파일은 `Docs/Work/APP-001/` 의 네 개다. `STATE.md` 는 엔진만 쓴다.

| 파일 | 내용 |
|---|---|
| `BRIEF.md` | 목적, 범위/제외, acceptance 기준, 제약, 정상·예외 시나리오. `TBD`/`TODO`/`UNSET` 만 있는 줄 제거 |
| `DOR.md` | 준비 체크리스트를 실제 상태로 |
| `ACCEPTANCE.json` | `{"criteria":[{"id":"AC-01","description":"...","checks":["unit","browser-e2e"]}]}`. `checks` 는 enabled command id |
| `CLARIFICATIONS.json` | 6개 분석 영역의 `finding` + `sources`, 질문과 사용자 답변. 미해결 질문이 있으면 사용자에게 묻고 기다린다 |

```console
python -m web_pipeline clarification-report --task APP-001
python -m web_pipeline prepare --task APP-001 --implementer claude
python -m web_pipeline run --task APP-001 --profile Baseline
python -m web_pipeline transition --task APP-001 --status READY
python -m web_pipeline transition --task APP-001 --status IN_PROGRESS
```

여기서 제품 코드를 구현한다. 필요할 때마다 `run --task APP-001 --profile Fast`.

```console
python -m web_pipeline transition --task APP-001 --status VERIFYING
python -m web_pipeline run --task APP-001 --profile Full
python -m web_pipeline transition --task APP-001 --status REVIEW
python -m web_pipeline review --task APP-001 --decision Docs/Work/APP-001/review-decision.json
python -m web_pipeline transition --task APP-001 --status DONE
python -m web_pipeline validate --task APP-001
```

- `clarification-report` 는 `CLEAR` 여야 `prepare` 가 통과한다.
- Baseline 은 코드 변경 **전**, DRAFT 에서만 실행된다. policy check 는 PASS 여야 하고, 그 외 check 는 실제로 실행된 FAIL 도 Baseline 으로 남는다(exit 1 이어도 `STATE.md` 의 `baseline_run` 확인).
- `prepare` 이후 task 문서·설정·인용 문서를 고치면 fingerprint 가 stale 이다. `revise --task APP-001 --reason "..."` 로 DRAFT 로 돌아가 다시 prepare + Baseline.
- 완료 프로필은 `verification-plan --task APP-001` 의 `profile` 이다: `verification.scopes` 가 없으면 `Full`, 있으면 `Task`.
- 완료 run 이 PASS 가 아니면 REVIEW 로 못 간다. 고치고(IN_PROGRESS/VERIFYING 에서) 다시 run 한다. 완료 run 뒤에 소스를 바꾸면 그 run 은 무효다.
- `review-decision.json`: `{"choice","rationale","alternatives":[≥1],"risks":[]}`. 사용 가능한 `pipeline-reviewer`가 diff와 증거를 검토한다. 기능이 없으면 별도 로컬 검토 후 자체 리뷰로 기록한다. 사람의 승인이 아니다.
- 증거는 `Reports/Pipeline/<run-id>/`(`summary.json`, `logs/`, `artifacts/`, `screenshots/`)에 남는다. DONE 이후 보존은 `archive --task APP-001`.

## 5. frontend task 의 스크린샷

`frontend` 도메인이 포함된 task 의 Task/Phase/Full/Release run 은 `$PIPELINE_EVIDENCE_DIR/screenshots/manifest.json` 이 없으면 FAIL 한다. 브라우저 check(`browser-e2e`)가 실제 페이지를 찍어 직접 쓴다.

```json
[
  {"kind": "desktop", "path": "screenshots/home-desktop.png", "width": 1440, "height": 900, "url": "http://127.0.0.1:4173/"},
  {"kind": "mobile", "path": "screenshots/home-mobile.png", "width": 390, "height": 844, "url": "http://127.0.0.1:4173/"}
]
```

- `desktop` 과 `mobile` 둘 다 필수. `path` 는 `screenshots/` 로 시작하는 run 상대 경로, `url` 은 비어 있지 않은 문자열.
- 선언한 `width`/`height` 가 설정의 `evidence`(기본 desktop 1440x900, mobile 390x844)와 같아야 하고, **디코딩한 이미지의 실제 픽셀 크기**도 같아야 한다. `fullPage: false` 로 찍고, `deviceScaleFactor` 가 1 이 아닌 기기 프로필(예: Playwright `devices['iPhone 13']`)은 픽셀 크기가 달라지므로 `page.setViewportSize` 를 쓰거나 screenshot 옵션 `scale: 'css'` 를 준다.
- Playwright 어댑터 예시는 프로젝트의 `Docs/Runbooks/FRONTEND.md`. 손으로 만든 이미지나 다른 run 의 파일을 복사해 넣지 않는다.

## 6. tier 별 필수 단계

| 단계 | T0 | T1 | T2 | T3 | T4 |
|---|---|---|---|---|---|
| `BRIEF.md`, `DOR.md`, `ACCEPTANCE.json`, `CLARIFICATIONS.json` | 필수 | 필수 | 필수 | 필수 | 필수 |
| `PLAN.md` | | | 필수 | 필수 | 필수 |
| `EXEC_PLAN.md` + ACCEPTED ADR(`attach --kind adr`, prepare 전) | | | | 필수 | 필수 |
| `RELEASE.md` | | | | | 필수 |
| design 승인(`approval-request --phase design` → 사용자 동의 → `approve`), READY 전 | | | | 필수 | 필수 |
| prepare, Baseline, 완료 run | 필수 | 필수 | 필수 | 필수 | 필수 |
| 리뷰 gate (DONE 전) | 없음 | `review` | `review` | 사용자 review 승인 | 사용자 review 승인 |
| `run --profile Release` (DONE 이후, release 승인) | | | | | 필수 |

보호 변경(`protected_changes`)이 붙은 task 는 tier 와 무관하게 T3 열을 따른다: 그 범위를 덮는 ADR, design/review 사용자 승인. `approval_policy: strict` 는 로컬 `review` 대신 서명된 승인을 요구한다. 요청한 tier 는 하한일 뿐이고, 엔진이 diff·도메인·path rule 로 더 높게 분류하면 높은 쪽이 적용된다. 승인 절차는 [approvals.md](approvals.md).

## 제품 작업으로 이어가기

[product-first.md](product-first.md)에 따라 요청된 첫 기능을 구현한다. 별도 시범 기능이나 범용 파이프라인 도구를 만들지 않는다. 작은 연결 기능은 단일 task로 충분하며, 기존 자료·명령·검증 증거를 재사용한다.
