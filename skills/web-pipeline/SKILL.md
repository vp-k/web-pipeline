---
name: web-pipeline
description: Adopt, configure, operate or audit the Web Development Pipeline - risk tiers T0-T4, tracked tasks under Docs/Work, real verification evidence, approval gates and a durable work queue. Use when the user asks for the web pipeline explicitly, or when the repository contains pipeline.config.yaml and the request is tracked development work, verification, review, status or an engine upgrade. Not for ordinary edits in repositories that have not adopted it.
---

# Web Development Pipeline

프로젝트 안에 복사된 **프로젝트 로컬 Python 엔진**을 운용하는 스킬이다. 플러그인 설치는 기능을 제공할 뿐, 프로젝트 준비 완료나 배포 권한이 아니다.

## 실행 방법 (두 가지뿐)

| 상황 | 명령 |
| --- | --- |
| 도입된 프로젝트 안의 모든 작업 | 프로젝트 루트에서 `python -m web_pipeline <command>` |
| 도입·진단·업그레이드·복원 | `python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" <doctor\|inspect\|adopt\|upgrade\|restore>` |

프로젝트 작업에 플러그인의 `kit/` 엔진을 대신 쓰지 않는다. 버전이 다를 수 있다. Python 3.11+, Git, `requirements-pipeline.txt` 의존성이 없으면 없다고 보고하고, 실행한 척하지 않는다.

## 무엇을 읽을지 (필요한 것만)

| 요청 | 읽을 것 |
| --- | --- |
| 처음 도입, 설정 | [references/quickstart.md](references/quickstart.md), [references/adoption.md](references/adoption.md), [references/config-cookbook.md](references/config-cookbook.md) |
| 작업 1건 수행·검증·재개 | 프로젝트의 `PIPELINE.md`, 해당 `Docs/Work/<TaskId>/`, [references/commands.md](references/commands.md), 예시는 [references/worked-example.md](references/worked-example.md) |
| 큐로 계속 개발 | [references/continuous.md](references/continuous.md) |
| 보호 변경·T3/T4·예외·Release 승인 | [references/approvals.md](references/approvals.md) |
| 오류 문자열, 막힘 | [references/troubleshooting.md](references/troubleshooting.md) |
| 상태 토큰·용어 | [references/glossary.md](references/glossary.md) |
| 업그레이드·복원 | [references/adoption.md](references/adoption.md)의 유지보수 절 |
| 리뷰·감사 | 상태·설정·보존된 증거를 **읽기만** 한다. 리뷰 요청은 도입·수정·상태 전이·새 검증·아카이브·배포 권한이 아니다 |

도메인 작업 전에는 그 도메인의 프로젝트 런북(`Docs/Runbooks/FRONTEND|BACKEND|API|DATABASE|SECURITY|BOUNDARIES.md`)만 읽는다. 무관한 런북을 전부 읽지 않는다. 시작은 항상 `python -m web_pipeline status`.

## 제품 작업 우선

첫 결과는 요청받은 기능의 동작과 검증이다. 기존 코드·문서·테스트를 재사용하고, 적용 도메인은 실제 범위로 지정한다. 전체 도메인 예시를 제품 요구사항으로 해석하지 않는다. 파이프라인 자체 개선·새 프레임워크·검사 대시보드를 제품 작업의 선행 조건으로 추가하지 않는다. 자세한 기준은 [references/product-first.md](references/product-first.md).

## 절대 규칙

1. 상태의 주인은 `Docs/Work/<TaskId>/STATE.md`와 엔진 전이뿐이다. 상태·실행 포인터·카운터를 손으로 고쳐 게이트를 통과하지 않는다.
2. 변경 **전에** Baseline을 잡는다. `PASS`, `FAIL`, `NOT_RUN`, `BLOCKED`, `NOT_APPLICABLE`, `INCONCLUSIVE`는 서로 다른 뜻이며 PASS만 PASS다.
3. PASS를 얻으려고 테스트·명령·요구사항을 약화·삭제·축소하지 않는다. 위험 등급은 올릴 수만 있다. 애매하면 높은 쪽.
4. 담당자·승인·날짜·리비전·명령·스크린샷·로그·결과를 지어내지 않는다.
5. `approval_policy: standard`에서 보호되지 않은 T0–T2는 사용자 승인 게이트가 없다. 요청 범위 안의 구현·수정·검증·로컬 리뷰는 단계마다 허락을 구하지 말고 계속한다. T1/T2 리뷰는 사용 가능한 `pipeline-reviewer`로 새 컨텍스트에서 수행한다. 기능이 없으면 별도 로컬 검토를 수행·기록하고 자체 리뷰임을 명시한다. 이는 사람의 승인이 아니다.
6. 보호 변경·T3/T4·예외·Release는 `approval-request`로 먼저 확인하고, 필요할 때만 그 단계의 결정을 한 번에 묶어 묻는다. 설계 승인은 구현 결과·예외·Release·운영 실행을 승인하지 않는다. 사용자 동의·서명 키·신원을 만들어내지 않는다.
7. 인프라·호스팅·배포·운영 데이터는 사용자 몫이다. 명시적 요청 없이는 계획·큐·완료 기준에 넣지 않는다. Release는 준비 상태 검증일 뿐 배포 허가가 아니다.
8. 새 도입의 누적 시간 기본값 `time_budget_mode: warn`은 경고만 한다. 강제 모드·실패/스텝 한도는 유지한다. 이미 받은 구체적 재개·추가 예산 요청은 다시 묻지 않고 한 번 적용한다. 이전 포괄 요청으로 반복 `loop renew`하지 않는다.
9. `WAITING`/`FAIL`은 원인 진단부터 한다. 범위 안의 수리·환경 복구·기록 전사·리스 복구는 기존 요청으로 진행한다. 판단 기준은 [references/continuation.md](references/continuation.md).

보고에는 작업 ID/리비전, 실제 상태, 실행된 check와 결과, 증거 경로, 실패, 남은 승인을 넣는다. 명령이 0으로 끝났다는 이유만으로 기능 완료라고 하지 않는다.
