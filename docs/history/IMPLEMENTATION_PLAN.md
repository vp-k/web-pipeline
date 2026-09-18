# Web Development Pipeline implementation plan

This plan implements the user's request to make the standalone web pipeline usable. It does not authorize production actions or create human approvals. The existing package self-test passed on Windows PowerShell 5.1 before implementation; that test covers structure and three classifications only.

## Architecture decision for this implementation

Use Python 3.11+ for a single cross-platform engine with JSON Schema (jsonschema), Ed25519 approval verification (cryptography), and image decoding (Pillow). Keep PowerShell entry points as adapters. JSON-compatible YAML remains the configuration format. This is the implementation proposal authorized by the user, not a fabricated approved production ADR.

## Milestones and acceptance

1. Shared foundation: schemas, safe paths, atomic writes, locks, fingerprints and versioned configuration. Reject malformed input, traversal, duplicate IDs and impossible profile requirements.
2. Governance: task creation/revision/state transitions, diff/path promotion, signed scoped human decisions, explicit exceptions and independent review. No status flag alone can establish verified completion.
3. Execution/evidence: argv commands, timeouts, iteration accounting, unique runs, content-addressed artifacts, browser manifests, Baseline/Fast/Full/Release. Every required check is executed or has a current approved exception.
4. Integration: one CLI, legacy PowerShell adapters, adoption tooling, CI kit tests plus strict project task scanning, documentation and a runnable example.
5. Adversarial verification: fake PASS, missing ADR, stale/forged approvals, stale source or code, role confusion, conditional approvals, schema errors, release without Full, migration profile mismatch, tampered images/logs, duplicate runs, retry/time limits and path escape are rejected.

## Delivery gates

- Unit and integration tests run on the available Windows/Python environment.
- CI matrix defines Linux/Python and Windows/Python plus PowerShell adapters; remote CI results are not assumed.
- A real sample lifecycle executes Baseline and Full and reaches its permitted gate with persisted evidence.
- Strict project configuration remains non-ready until real commands, Git history, source files and external approver keys are supplied.
- All prior review findings are mapped to implementation, tests or an explicitly documented boundary.

## Work split

- sol governance agent: policy.py, state.py, approval.py and related tests.
- sol execution agent: runner.py and evidence.py and related tests.
- sol integration agent: CLI/adapters, installation/example/CI, related tests and operational documentation.
- primary agent: common.py, configuration/schema contracts, integration review, test execution and fixes.

## Recovery and progress

Existing product files are preserved; old entry points are adapted without silently interpreting version 1 data as version 2. No production command is provided. A v1 project must explicitly migrate its configuration/task data; stale approvals never migrate as approved.

- Baseline: original `Scripts/Test-Pipeline.ps1 -AllowUnconfigured` PASS with expected UNSET warnings.
- Work authorization: user's current implementation request. Approval of external project decisions/releases remains separate.

## 구현 및 검증 결과 — 2026-09-09

5개 단계의 구현과 로컬 검증을 완료했다. Sol 서브에이전트 3개가 거버넌스, 실행·증거, CLI·설치·문서 작업을 분담했고, 주 에이전트가 공통 엔진·스키마와 통합 검증을 담당했다.

- 실제 프로세스 실행, 외부 Ed25519 서명 검증, 상태 전이, 증거 무결성, T4 릴리스 승인, 실패 Baseline, 완료 작업 보관을 포함한 **51개 테스트 통과**. 실패 0, 오류 0, Skip 0.
- [실행 보고서](Reports/Pipeline/delivery-20260908T235223Z-766e485b/delivery-validation.json), [전체 테스트 로그](Reports/Pipeline/delivery-20260908T235223Z-766e485b/unittest.log).
- Python 3.13.14 / Windows 11에서 실행했다. 모듈 컴파일, kit 검증, PowerShell 5.1 policy 어댑터도 통과했다.
- 설치 예제는 격리된 임시 Git 저장소에서 실제 단위 검사를 실행해 Baseline/Full 통과 후 REVIEW에 도달했다. 예제 증거는 `E:/code/web-pipeline-example-evidence-20260909-v2`에 보존했다. 예제는 실행기 사용법을 보여주는 최소 검사이며 실제 웹 애플리케이션의 검증 결과가 아니다.
- 회귀 테스트의 서명 키는 임시 테스트 키다. 실제 사람의 승인, 실제 제품 DONE, Production 배포를 생성하지 않았다.
- 배포 키트는 의도적으로 `ready: false`다. 적용 프로젝트의 검사 명령·소스 문서·Git 기준점·외부 승인 키·CI 권한을 연결해야 프로젝트 운영을 시작할 수 있다.
- Linux와 PowerShell 7 검증은 CI에 정의했지만 원격 실행 결과는 아직 없다. Production 실행은 이 엔진의 권한 범위 밖이다.

사용 순서와 명령은 [README](README.md), 지적사항별 해결 내역과 외부 통제 경계는 [REVIEW_RESOLUTION](REVIEW_RESOLUTION.md)을 따른다.

### 후속 전체 리뷰 수정 — v2.1

위 51개 결과는 초기 v2 구현 당시의 기록이다. 이후 재현한 11개 결함을 수정하고 회귀 테스트 18개를 추가했다. 최신 결과는 [69개 테스트 통과 보고서](Reports/Pipeline/delivery-20260909T032900Z-8d272285/delivery-validation.json)와 [수정 계획·실행 결과](REMEDIATION_PLAN.md)를 따른다. 원격 CI 및 실제 웹 프로젝트 연결은 별도 검증 대상으로 남아 있다.
