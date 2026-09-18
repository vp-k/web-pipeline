# Config Cookbook

`pipeline.config.yaml` 은 JSON 문법만 허용한다. 도입 단계에서 **저장소에 실제로 존재하고 직접 실행해 본 명령**만 배선한다. 통과용 더미 명령(`node -e ""`, 항상 0 을 돌려주는 스크립트)은 증거 위조다. `ready: true` 이후의 설정 편집은 그 자체가 T3 통제 변경이다(§6).

레시피는 전체 도구를 새로 만들라는 요구가 아니다. 기존 명령을 실제 도메인에 연결하고, 없는 기능의 검사나 Release 전용 준비를 개발 선행 조건으로 만들지 않는다. [제품 우선 기준](product-first.md)을 따른다.

## 1. 표기법

레시피는 파일 전체가 아니라 **패치**다. 점 표기 키는 그 경로의 값을 통째로 교체한다. 예외 둘: `verification.commands` 는 실제 파일에서 배열이며, 패치의 `<id>` 항목 필드를 덮어쓰고 `enabled: true` 로 바꾼다(기본 목록에 없는 id 는 새 항목, 적지 않은 필드는 기본값). `risk.path_rules` 는 배열 끝에 append 한다. 완성된 항목 하나의 실제 모양:

```json
{"id": "lint", "enabled": true, "profiles": ["Policy", "Baseline", "Fast", "Full", "Release"],
 "argv": ["npx", "eslint", "."], "cwd": ".", "timeout_seconds": 300, "artifacts": [], "environment": "test"}
```

명령 규칙:
- `argv` 는 문자열 배열. 셸 문자열, `cmd`, `sh -c`/`bash -c`, `powershell -Command` 는 거부된다. 파이프·`&&` 가 필요하면 스크립트 파일을 두고 `["node","tools/x.mjs"]`, `["python","tools/x.py"]`, `["bash","tools/x.sh"]`, `["pwsh","-NoProfile","-File","tools/x.ps1"]` 로 부른다.
- `argv[0]` 은 PATH/PATHEXT 로 해석된다. Windows 에서도 `npm`, `npx`, `pnpm` 그대로.
- `cwd` 는 루트 기준 상대 경로이며 존재해야 한다. `timeout_seconds` 1–7200. `environment` 에 `production` 금지.
- 검증 명령은 소스를 바꾸지 않는다(`prettier --check`, `ruff format --check`, `--fix` 없음). 실행 중 추적 트리가 바뀌면 `source changed during verification` 으로 FAIL.
- 명령이 받는 환경 변수: `PIPELINE_EVIDENCE_DIR`(이번 run 디렉터리), `PIPELINE_CHECK_ID`, `PIPELINE_TASK_ID`, `PIPELINE_PROFILE`. 산출물은 `$PIPELINE_EVIDENCE_DIR/artifacts/`, 스크린샷은 `$PIPELINE_EVIDENCE_DIR/screenshots/` 에만 쓴다. `artifacts` 의 glob 은 run 디렉터리 기준이고 매칭 파일이 없으면 FAIL.

## 2. 기본 check id

B=Baseline, F=Fast, U=Full, R=Release(Release 실행은 Full 목록을 포함). "보호 규칙" 은 해당 `protected_changes` 가 붙은 task 의 Full/Release 에 추가로 요구되는 경우.

| id | 목적 | 도메인 요구 | 보호 규칙 |
|---|---|---|---|
| `secret-detection` | 비밀값 스캔 | `policy_checks` (모든 run) | secrets_credentials |
| `dependency-policy` | 의존성 허용 정책 | `policy_checks` (모든 run) | |
| `format` | 포맷 검사 | frontend FUR, backend FUR | |
| `lint` | 정적 분석 | frontend BFUR, backend BFUR | |
| `typecheck` | 타입 검사 | frontend BFUR | |
| `unit` | 단위 테스트 | frontend/backend/authentication/authorization BFUR, privacy/payment BF | |
| `build` | 빌드 | frontend BUR, backend BUR, deployment BFUR | core_architecture, major_framework_sdk |
| `integration` | 실제 DB·서비스 통합 테스트 | backend/api/privacy/external_integration UR, database/authentication/authorization/payment BUR | payment, wallet_balance, external_integration_contract, core_architecture, major_framework_sdk |
| `smoke` | 기동 후 핵심 경로 | frontend/backend/api/infrastructure/deployment UR | dns_cdn_waf |
| `browser-e2e` | 브라우저 E2E + 스크린샷 manifest | frontend UR | |
| `accessibility` | 접근성 | frontend UR | |
| `contract-provider` | 제공자 계약 테스트 | api/external_integration BFUR, payment UR | public_api_contract, webhook_contract, external_integration_contract |
| `contract-consumer` | 소비자 계약 테스트 | api BFUR, external_integration BUR | 위와 같음 |
| `contract-compatibility` | 계약 하위 호환 비교 | api UR | public_api_contract |
| `schema-check` | DB 스키마 검증 | database BFUR | database_schema |
| `migration-dry-run` | 일회용 DB 마이그레이션 | database UR | database_schema, destructive_migration |
| `rollback-validation` | 롤백 검증 | database UR | database_schema |
| `restore-validation` | 백업 복원 | database R | destructive_migration |
| `security` | 보안 테스트/SAST | security BFUR, authentication/authorization/privacy/payment/infrastructure UR, frontend/backend/api R | authentication, session_cookie, csrf_cors_csp, encryption, secrets_credentials, personal_data_pii, payment, infrastructure, dns_cdn_waf |
| `session-tests` | 세션/쿠키 | authentication UR | authentication, session_cookie |
| `authorization-tests` | 서버 권한 거부 | authentication UR, authorization UR | authentication, authorization_rbac |
| `privacy-tests` | 개인정보 처리 | privacy UR | personal_data_pii, production_data |
| `payment-tests` | 결제 | payment UR | payment, wallet_balance |
| `webhook-tests` | 웹훅 서명·재전송 | external_integration UR | webhook_contract |
| `infra-validate` | IaC 검증 | infrastructure BFUR | infrastructure, dns_cdn_waf |
| `dependency-audit` | 취약 의존성 감사 | frontend/backend/security/infrastructure R | major_framework_sdk |
| `performance` | 성능 예산 | frontend R, backend R | |
| `production-build` | 운영 설정 빌드 | frontend/backend/deployment R | production_deployment |
| `deployment-smoke` | 배포 준비 스모크 | deployment R | production_deployment |
| `recovery-validation` | 복구 절차 | payment/infrastructure/deployment R | wallet_balance, destructive_migration, production_data, production_deployment |

## 3. 활성화 규칙

`ready: true` 프로젝트는 설정 로드 때마다 검사하고, 어기면 모든 명령이 실패한다.

- `policy_checks` 전부, 그리고 `supported_domains` 각 도메인의 **Baseline·Fast·Full 세 목록의 모든 id** 가 `enabled: true` + 비어 있지 않은 `argv` + 존재하는 `cwd` 여야 한다(`Required project command <id> is disabled`). Release 전용 check는 일반 개발 준비를 막지 않는다. 정의와 프로필의 구조는 검사하며, 실제 Release 실행에서는 빠지거나 비활성인 check가 NOT_RUN으로 남아 통과하지 못한다.
- `requirements` 는 12개 도메인 키를 전부 유지한다. 목록의 id 는 정의돼 있고 그 프로필을 `profiles` 에 포함해야 한다. `policy_checks` 의 id 는 `Policy` 프로필 필수.
- 실행 시 필요한 check 가 disabled/미정의면 `NOT_RUN` → run FAIL.

순서: (1) `supported_domains` 를 실제 범위로 좁힌다 → (2) 그 도메인의 필수 id 를 표에서 뽑는다 → (3) 도구가 있는 id 는 배선한다 → (4) 도구가 **없는** id 는 사용자와 합의해 그 도메인의 `requirements` 와 `policy_checks` 에서 빼고 보고한다. 추가는 자유다. `supported_domains` 밖이라도 path rule 이 도메인을 붙이면 그 check 가 요구된다. 예: `package.json`·lock 파일 변경 → `security` + `major_framework_sdk`(T3) → `security`, `dependency-audit`, `integration`, `build` 필요.

`test_report`(선택)는 exit code 대신 케이스별 판정을 강제한다. 받는 형식은 **엔진 JSON(`Schemas/test-results.schema.json`) 하나뿐**이다. JUnit XML, Jest/Vitest/pytest 기본 JSON 은 받지 않는다. 커스텀 reporter 가 `$PIPELINE_EVIDENCE_DIR/<path>` 에 직접 쓴다:

```json
{"schema_version": "1.0", "run_id": "<PIPELINE_EVIDENCE_DIR 의 basename>", "check_id": "<PIPELINE_CHECK_ID>",
 "completed": true, "errors": [],
 "tests": [{"id": "signup.spec.ts::rejects bad email", "group": "e2e", "status": "passed", "duration_ms": 412}]}
```

`status`: `passed|failed|error|skipped`. 파일 누락·`completed:false`·중복 id·`min_tests` 미달·`max_skipped` 초과·`required_groups` 미실행·failed/error 케이스는 exit 0 이어도 FAIL. 재시도는 끈다(`retries: 0`). Playwright 참고 구현은 `${CLAUDE_PLUGIN_ROOT}/examples/web/reporter.cjs`. reporter 가 없으면 `test_report` 를 생략한다. lint/build 에는 붙이지 않는다.

## 4. 스택별 레시피

### (a) Next.js App Router + npm (Vitest, Playwright)

```json
{
  "project.supported_domains": ["frontend"],
  "project.respect_gitignore": true,
  "project.generated_paths": [".next", "coverage", "test-results", "playwright-report"],
  "verification.policy_checks": ["secret-detection"],
  "verification.requirements.frontend": {
    "Baseline": ["lint", "typecheck", "unit", "build"],
    "Fast": ["format", "lint", "typecheck", "unit"],
    "Full": ["format", "lint", "typecheck", "unit", "browser-e2e", "accessibility", "build", "smoke"],
    "Release": ["dependency-audit", "production-build"]
  },
  "verification.commands": {
    "secret-detection": {"argv": ["gitleaks", "git", "--redact", "--no-banner", "."]},
    "format": {"argv": ["npx", "prettier", "--check", "."]},
    "lint": {"argv": ["npx", "eslint", "."]},
    "typecheck": {"argv": ["npx", "tsc", "--noEmit"]},
    "unit": {"argv": ["npx", "vitest", "run"]},
    "build": {"argv": ["npx", "next", "build"], "timeout_seconds": 900},
    "production-build": {"argv": ["npx", "next", "build"], "timeout_seconds": 900},
    "browser-e2e": {"argv": ["npx", "playwright", "test", "--project=e2e"], "timeout_seconds": 1200,
                    "artifacts": ["screenshots/manifest.json"]},
    "accessibility": {"argv": ["npx", "playwright", "test", "--project=a11y"], "timeout_seconds": 900},
    "smoke": {"argv": ["npx", "playwright", "test", "--project=smoke"], "timeout_seconds": 900},
    "dependency-audit": {"argv": ["npm", "audit", "--audit-level=high"]}
  }
}
```

- `next lint` 는 Next.js 16 에 없다. ESLint CLI 를 쓴다.
- `--project=e2e|a11y|smoke` 는 `playwright.config` 의 `projects[].name`. a11y 는 `@axe-core/playwright` 단언, smoke 는 `next start` 로 띄운 빌드에 대한 핵심 경로. `webServer` 는 비운영 설정.
- `browser-e2e` 는 `screenshots/manifest.json` 을 반드시 쓴다(desktop 1440x900 + mobile 390x844, 프로젝트 `Docs/Runbooks/FRONTEND.md`).
- `security`·`performance`·`dependency-policy` 는 실제 도구(SAST, Lighthouse CI 등)가 생기면 목록에 되돌린다.
- `app/api/**` route handler 가 있으면 `backend`, 계약 파일과 계약 테스트가 있으면 `api` 를 `supported_domains` 에 추가하고 (c)를 따른다.

### (b) Vite + React SPA (Vitest, Playwright)

(a)와 같고 다음만 다르다.

```json
{
  "project.generated_paths": ["dist", "coverage", "test-results", "playwright-report"],
  "verification.commands": {
    "typecheck": {"argv": ["npx", "tsc", "--noEmit", "-p", "tsconfig.app.json"]},
    "build": {"argv": ["npx", "vite", "build"]},
    "production-build": {"argv": ["npx", "vite", "build", "--mode", "production"]},
    "browser-e2e": {"argv": ["npx", "playwright", "test", "--project=e2e"], "timeout_seconds": 1200,
                    "artifacts": ["screenshots/manifest.json"],
                    "test_report": {"path": "artifacts/e2e-tests.json", "min_tests": 1, "max_skipped": 0, "required_groups": ["e2e"]}}
  }
}
```

`test_report` 는 참고 reporter 를 저장소에 복사해 출력 경로를 `artifacts/e2e-tests.json` 으로 맞추고 `playwright.config` 의 `reporter` 에 등록했을 때만 넣는다. 그룹은 테스트 제목의 `[e2e]` 접두사. `outputDir` 을 `path.join(process.env.PIPELINE_EVIDENCE_DIR, 'artifacts/playwright')` 로 돌리면 소스 트리가 깨끗하다.

### (c) Express/NestJS API + 실제 Postgres (testcontainers)

```json
{
  "project.supported_domains": ["backend", "api", "database"],
  "project.generated_paths": ["dist", "coverage"],
  "verification.policy_checks": ["secret-detection"],
  "verification.requirements.backend": {
    "Baseline": ["lint", "typecheck", "unit", "build"],
    "Fast": ["format", "lint", "typecheck", "unit"],
    "Full": ["format", "lint", "typecheck", "unit", "integration", "build", "smoke"],
    "Release": ["dependency-audit", "production-build"]
  },
  "verification.requirements.api": {
    "Baseline": ["contract-provider"], "Fast": ["contract-provider"],
    "Full": ["contract-provider", "contract-compatibility", "integration", "smoke"], "Release": []
  },
  "verification.requirements.database": {
    "Baseline": ["schema-check", "integration"], "Fast": ["schema-check"],
    "Full": ["schema-check", "integration", "migration-dry-run"], "Release": []
  },
  "verification.commands": {
    "secret-detection": {"argv": ["gitleaks", "git", "--redact", "--no-banner", "."]},
    "format": {"argv": ["npx", "prettier", "--check", "."]},
    "lint": {"argv": ["npx", "eslint", "."]},
    "typecheck": {"argv": ["npx", "tsc", "--noEmit"]},
    "unit": {"argv": ["npx", "vitest", "run", "--project", "unit"]},
    "integration": {"argv": ["npx", "vitest", "run", "--project", "integration"], "timeout_seconds": 1800},
    "contract-provider": {"argv": ["npx", "vitest", "run", "--project", "contract"], "timeout_seconds": 900},
    "contract-compatibility": {"argv": ["node", "tools/contract-compat.mjs"]},
    "build": {"argv": ["npx", "tsc", "-p", "tsconfig.build.json"]},
    "production-build": {"argv": ["npx", "tsc", "-p", "tsconfig.build.json"]},
    "smoke": {"argv": ["node", "tools/smoke.mjs"], "timeout_seconds": 600},
    "schema-check": {"argv": ["npx", "prisma", "validate"]},
    "migration-dry-run": {"argv": ["node", "tools/migrate-dry-run.mjs"], "timeout_seconds": 900},
    "dependency-audit": {"argv": ["npm", "audit", "--audit-level=high"]}
  }
}
```

- `--project <name>` 은 Vitest `projects` 의 이름. Jest 는 suite 별 설정 파일: `["npx","jest","--config","jest.integration.config.js"]`. NestJS 빌드는 `["npx","nest","build"]`.
- `integration` 은 `@testcontainers/postgresql` 로 **실제 Postgres** 를 띄우고 **실제 마이그레이션**을 적용한 뒤 테스트한다. mock·SQLite·schema sync 대체 금지. Docker 가 없으면 FAIL 로 보고하고 목록에서 빼지 않는다.
- `tools/*.mjs` 는 프로젝트가 작성해 리뷰하는 스크립트. `smoke.mjs`: 빌드 산출물을 비운영 설정으로 기동 → health/핵심 경로 호출 → 종료. `migrate-dry-run.mjs`: 일회용 컨테이너에 전체 마이그레이션 적용. `contract-compat.mjs`: `base_ref` 의 계약 파일과 현재 파일의 브레이킹 변경 비교.
- 위 패치는 소비자가 없어 `contract-consumer` 를, 도구가 없어 `rollback-validation`·`restore-validation`·`security`·`performance` 를 뺀 상태다. `*.sql`·`*migration*` 경로는 T3 `database_schema` 로 승격되어 `rollback-validation` 을 요구하므로 마이그레이션을 다루기 전에 배선한다.

### (d) FastAPI/Django + pytest, ruff, mypy

```json
{
  "project.supported_domains": ["backend"],
  "project.generated_paths": [".mypy_cache", ".ruff_cache", "htmlcov"],
  "verification.policy_checks": ["secret-detection"],
  "verification.requirements.backend": {
    "Baseline": ["lint", "typecheck", "unit", "build"],
    "Fast": ["format", "lint", "typecheck", "unit"],
    "Full": ["format", "lint", "typecheck", "unit", "integration", "build", "smoke"],
    "Release": []
  },
  "verification.commands": {
    "secret-detection": {"argv": ["gitleaks", "git", "--redact", "--no-banner", "."]},
    "format": {"argv": ["ruff", "format", "--check", "."]},
    "lint": {"argv": ["ruff", "check", "."]},
    "typecheck": {"argv": ["mypy", "."]},
    "unit": {"argv": ["python", "-m", "pytest", "tests/unit", "-p", "no:cacheprovider"],
             "test_report": {"path": "artifacts/unit-tests.json", "min_tests": 1, "max_skipped": 0, "required_groups": ["unit"]}},
    "integration": {"argv": ["python", "-m", "pytest", "tests/integration", "-p", "no:cacheprovider"], "timeout_seconds": 1800},
    "smoke": {"argv": ["python", "-m", "pytest", "tests/smoke", "-p", "no:cacheprovider"], "timeout_seconds": 600},
    "build": {"argv": ["python", "-m", "compileall", "-q", "app"]}
  }
}
```

- 엔진을 프로젝트 venv 가 활성화된 셸에서 실행해야 같은 `python`/`ruff`/`mypy` 로 해석된다. Django 는 `build` 에 `["python","manage.py","check"]`. `.pyc` 는 엔진이 `PYTHONPYCACHEPREFIX` 로 run 디렉터리에 격리하고, `-p no:cacheprovider` 는 `.pytest_cache` 를 만들지 않는다.
- `test_report` 용 pytest 어댑터(`tests/conftest.py`). 그룹은 `tests/<group>/...` 디렉터리 이름. 없으면 `test_report` 를 뺀다.

```python
import json, os, pathlib
_cases = {}

def pytest_runtest_logreport(report):
    case = _cases.setdefault(report.nodeid, {"status": "skipped", "ms": 0.0})
    case["ms"] += report.duration * 1000
    if report.failed:
        case["status"] = "failed" if report.when == "call" else "error"
    elif report.when == "call" and report.passed and case["status"] == "skipped":
        case["status"] = "passed"

def pytest_sessionfinish(session, exitstatus):
    root = os.environ.get("PIPELINE_EVIDENCE_DIR")
    if not root:
        return
    check = os.environ["PIPELINE_CHECK_ID"]
    tests = [{"id": nodeid, "group": pathlib.PurePosixPath(nodeid).parts[1], "status": c["status"],
              "duration_ms": round(c["ms"])} for nodeid, c in sorted(_cases.items())]
    out = pathlib.Path(root, "artifacts", f"{check}-tests.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema_version": "1.0", "run_id": pathlib.Path(root).name, "check_id": check,
                               "completed": int(exitstatus) in (0, 1), "errors": [], "tests": tests}), encoding="utf-8")
```

### (e) Go API

```json
{
  "project.supported_domains": ["backend"],
  "project.generated_paths": ["bin", "coverage"],
  "verification.policy_checks": ["secret-detection"],
  "verification.requirements.backend": {
    "Baseline": ["lint", "unit", "build"], "Fast": ["format", "lint", "unit"],
    "Full": ["format", "lint", "unit", "integration", "build"], "Release": []
  },
  "verification.commands": {
    "secret-detection": {"argv": ["gitleaks", "git", "--redact", "--no-banner", "."]},
    "format": {"argv": ["python", "tools/gofmt_check.py"]},
    "lint": {"argv": ["go", "vet", "./..."]},
    "unit": {"argv": ["go", "test", "./..."], "timeout_seconds": 900},
    "integration": {"argv": ["go", "test", "-tags=integration", "./..."], "timeout_seconds": 1800},
    "build": {"argv": ["go", "build", "./..."], "timeout_seconds": 900}
  }
}
```

`gofmt -l` 은 차이가 있어도 exit 0 이므로 래퍼가 필요하다. `tools/gofmt_check.py`:

```python
import subprocess, sys
out = subprocess.run(["gofmt", "-l", "."], capture_output=True, text=True, check=True).stdout.strip()
if out:
    print(out)
    sys.exit(1)
```

`integration` 은 `//go:build integration` 태그 + testcontainers-go 의 실제 DB. 기본 rule `*.go` → backend T1.

### (f) 정적 사이트 (Astro)

```json
{
  "project.supported_domains": ["frontend"],
  "project.generated_paths": ["dist", ".astro", "test-results", "playwright-report"],
  "verification.policy_checks": ["secret-detection"],
  "verification.requirements.frontend": {
    "Baseline": ["typecheck", "build"], "Fast": ["format", "typecheck"],
    "Full": ["format", "typecheck", "build", "browser-e2e", "accessibility"], "Release": []
  },
  "verification.commands": {
    "secret-detection": {"argv": ["gitleaks", "git", "--redact", "--no-banner", "."]},
    "format": {"argv": ["npx", "prettier", "--check", "."]},
    "typecheck": {"argv": ["npx", "astro", "check"]},
    "build": {"argv": ["npx", "astro", "build"], "timeout_seconds": 900},
    "browser-e2e": {"argv": ["npx", "playwright", "test", "--project=e2e"], "timeout_seconds": 900,
                    "artifacts": ["screenshots/manifest.json"]},
    "accessibility": {"argv": ["npx", "playwright", "test", "--project=a11y"], "timeout_seconds": 900}
  }
}
```

`astro check` 는 `@astrojs/check` + `typescript` 가 필요하고 오류 시 exit 1. 단위 테스트·lint 가 없는 사이트라 뺐다. 정적 프로젝트의 `boundaries` 는 browser/shared component 와 `"contracts": []` 만 선언한다.

### (g) 모노레포 `frontend/` + `backend/` (boundaries + scopes)

기본 id 는 `cwd` 가 하나뿐이므로 패키지별 id 를 만들고 `requirements` 가 그 id 를 가리키게 한다.

```json
{
  "project.supported_domains": ["frontend", "backend", "api"],
  "project.generated_paths": ["frontend/dist", "frontend/test-results", "frontend/playwright-report", "backend/dist", "coverage"],
  "verification.policy_checks": ["secret-detection"],
  "verification.requirements.frontend": {
    "Baseline": ["web-lint", "web-typecheck", "web-unit", "web-build"],
    "Fast": ["web-format", "web-lint", "web-typecheck", "web-unit"],
    "Full": ["web-format", "web-lint", "web-typecheck", "web-unit", "web-build", "browser-e2e"], "Release": []
  },
  "verification.requirements.backend": {
    "Baseline": ["api-lint", "api-unit", "api-build"], "Fast": ["api-format", "api-lint", "api-unit"],
    "Full": ["api-format", "api-lint", "api-unit", "api-build", "integration"], "Release": []
  },
  "verification.requirements.api": {
    "Baseline": ["contract-provider", "contract-consumer"], "Fast": ["contract-provider", "contract-consumer"],
    "Full": ["contract-provider", "contract-consumer", "contract-compatibility", "integration"], "Release": []
  },
  "verification.commands": {
    "secret-detection": {"argv": ["gitleaks", "git", "--redact", "--no-banner", "."]},
    "boundary-imports": {"argv": ["node", "Scripts/boundary-graph.cjs", "--tsconfig", "tsconfig.json"],
                         "timeout_seconds": 120, "artifacts": ["artifacts/boundary-graph.json"]},
    "web-format": {"argv": ["npx", "prettier", "--check", "."], "cwd": "frontend"},
    "web-lint": {"argv": ["npx", "eslint", "."], "cwd": "frontend"},
    "web-typecheck": {"argv": ["npx", "tsc", "--noEmit", "-p", "tsconfig.app.json"], "cwd": "frontend"},
    "web-unit": {"argv": ["npx", "vitest", "run"], "cwd": "frontend"},
    "web-build": {"argv": ["npx", "vite", "build"], "cwd": "frontend"},
    "browser-e2e": {"argv": ["npx", "playwright", "test"], "cwd": "frontend", "timeout_seconds": 1200,
                    "artifacts": ["screenshots/manifest.json"]},
    "api-format": {"argv": ["npx", "prettier", "--check", "."], "cwd": "backend"},
    "api-lint": {"argv": ["npx", "eslint", "."], "cwd": "backend"},
    "api-unit": {"argv": ["npx", "vitest", "run", "--project", "unit"], "cwd": "backend"},
    "api-build": {"argv": ["npx", "tsc", "-p", "tsconfig.build.json"], "cwd": "backend"},
    "integration": {"argv": ["npx", "vitest", "run", "--project", "integration"], "cwd": "backend", "timeout_seconds": 1800},
    "contract-provider": {"argv": ["npx", "vitest", "run", "--project", "contract"], "cwd": "backend"},
    "contract-consumer": {"argv": ["npx", "vitest", "run", "--project", "contract"], "cwd": "frontend"},
    "contract-compatibility": {"argv": ["node", "tools/contract-compat.mjs"]}
  },
  "boundaries": {
    "source_patterns": ["contracts/*"],
    "components": [
      {"id": "web", "runtime": "browser", "paths": ["frontend/src/*"], "depends_on": []},
      {"id": "api", "runtime": "server", "paths": ["backend/src/*"], "depends_on": []}
    ],
    "contracts": [{"id": "http-api", "paths": ["contracts/*"], "provider": "api", "consumers": ["web"],
      "checks": {"provider": "contract-provider", "consumer": "contract-consumer",
                 "compatibility": "contract-compatibility", "integration": "integration"}}],
    "dependency_check": "boundary-imports",
    "server_only_packages": ["pg", "prisma", "@prisma/client", "bcrypt", "jsonwebtoken"]
  },
  "verification.scopes": {
    "components": [
      {"id": "web", "paths": ["frontend/src/*"], "depends_on": ["api"], "domains": ["frontend"],
       "checks": {"Task": ["web-format", "web-lint", "web-typecheck", "web-unit", "web-build", "browser-e2e"], "Phase": ["browser-e2e"]}},
      {"id": "api", "paths": ["backend/src/*"], "depends_on": [], "domains": ["backend", "api"],
       "checks": {"Task": ["api-format", "api-lint", "api-unit", "api-build", "integration"], "Phase": ["integration"]}}
    ],
    "task_checks": [],
    "phase_checks": ["browser-e2e", "integration"],
    "broad_paths": ["tsconfig.json", "contracts/*"]
  }
}
```

boundaries:
- 다섯 키 모두 필수. `dependency_check` 명령은 다섯 프로필 전부 + `cwd: "."` + enabled, `artifacts/boundary-graph.json` 을 낸다. 제공 어댑터 `Scripts/boundary-graph.cjs` 는 Node 와 프로젝트의 TypeScript(>=5 <7)가 필요하고 JS/TS 만 해석한다.
- 의존 허용: browser→browser/shared, server→server/shared, shared→shared. `web` 은 `api` 를 `depends_on` 할 수 없고 연결은 `contracts` 로 표현한다. provider 는 server runtime, contract check 는 Full+Release 프로필 필수이고 `dependency_check` id 를 재사용할 수 없다.
- `source_patterns` + component `paths` 가 모든 소스 파일을 정확히 하나의 소유자로 덮어야 한다. 매칭 파일이 없는 component/contract 는 오류. 패턴은 `/` 구분, `./` 접두사 금지, `*` 는 `/` 도 넘는다.
- 없이 시작해도 된다. `validate` 가 `NOT_CONFIGURED` 경고만 낸다.

scopes:
- `boundaries` 가 있으면 component id 와 `paths` 가 두 모델에서 정확히 같아야 한다. `depends_on` 은 달라도 된다: scopes 의 `"web" depends_on ["api"]` 는 "api 가 바뀌면 web 의 Task check 도 실행".
- component `domains` ⊆ `supported_domains`. scopes 의 모든 check 는 enabled + `Full` 프로필. `phase_checks` 최소 1개.
- 설정하면 완료 프로필이 `Full` 에서 `Task`/`Phase` 로 바뀌고 `SCOPE.json` 을 쓸 수 있다. 다음 경우 프로젝트 전체로 확장된다(`verification-plan` 의 `reasons`): T3/T4·보호 변경, `broad_paths`, 내장 broad 경로(`pipeline.config.yaml`, `package.json`, `pyproject.toml`, `requirements*.txt`, `*.lock`/`*-lock.json`/`*-lock.yaml`/`*.lockb`/`*npm-shrinkwrap.json`, `*go.mod`/`*go.sum`, `web_pipeline/*`, `Schemas/*`/`schemas/*`, `Scripts/*`/`scripts/*`, `.github/*`, `Docs/Governance/*`, `Docs/Architecture/*`, `AGENTS.md`, `PIPELINE.md`, `CLAUDE.md`), 그리고 **어느 component 에도 속하지 않거나 둘 이상에 속하는 변경 경로**(`README.md`, `contracts/*` 등). 확장은 오류가 아니다.

## 5. 출력 경로

`project.respect_gitignore: true` 는 Git 이 무시하는 파일을 소스 digest 에서 제외한다. `.next/`, `dist/`, `coverage/`, 캐시가 `.gitignore` 에 있으면 추가 설정이 필요 없다. 이 키가 없거나 `false` 면 검증 중 생기는 모든 출력을 `generated_paths` 에 루트 기준 정확한 경로로 적는다(`dist` 는 루트의 `dist` 만. 모노레포는 `frontend/dist`). 항상 제외되는 이름: `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `.pipeline-locks`, `.pipeline-upgrades`. `generated_paths`/`report_root` 는 `Docs`, `Scripts`, `Schemas`, `Templates`, `web_pipeline`, `.github`, `sources` 문서와 겹칠 수 없고 그 아래에 Git 추적 파일이 있으면 거부된다(`.gitkeep` 제외).

## 6. `risk.path_rules` 조정

- 매칭은 저장소 상대 경로 **전체**에 대한 대소문자 구분 `fnmatch`. `*` 는 `/` 를 넘는다. 기본 rule 상당수가 넓은 부분 문자열이다: `*auth*` 는 `src/pages/authors.tsx` 도 T3 `authentication` 으로, `*session*`·`*secret*`·`*payment*`·`*wallet*`·`*migration*`·`*webhook*`·`*.env*` 도 같은 식으로 올린다. 잠금 파일은 실제 파일명 패턴(`*.lock`, `*-lock.json`, `*-lock.yaml`, `*.lockb`, `*npm-shrinkwrap.json`, `*go.sum`, `*go.mod`)만 잡으므로 `BlockList.tsx`·`useClock.ts` 는 승격되지 않는다.
- rule 은 **승격만** 한다: 매칭된 rule 의 tier 최댓값, domains·protected_changes 합집합. 좁은 rule 을 더해도 넓은 rule 의 효과는 사라지지 않는다. 오탐을 없애려면 넓은 rule 자체를 정확한 rule 로 **교체**해야 하고, 이는 보호를 줄이는 결정이므로 사용자 승인 대상이다. 확신이 없으면 넓은 채로 두고 높은 tier 를 받아들인다.
- 프로젝트 구조에 맞는 정확한 rule 을 추가한다(append):

```json
{
  "risk.path_rules": [
    {"pattern": "backend/src/modules/auth/*", "domains": ["authentication"], "protected_changes": ["authentication"], "tier": "T3"},
    {"pattern": "backend/prisma/migrations/*", "domains": ["database"], "protected_changes": ["database_schema"], "tier": "T3"},
    {"pattern": "contracts/*", "domains": ["api"], "protected_changes": [], "tier": "T2"},
    {"pattern": "backend/src/*.ts", "domains": ["backend"], "protected_changes": [], "tier": "T1"},
    {"pattern": "frontend/src/*.ts", "domains": ["frontend"], "protected_changes": [], "tier": "T1"}
  ]
}
```

- 기본 확장자 rule 은 `*.tsx`, `*.vue`, `*.css`, `*.go`, `*.php` 뿐이다. `.ts`, `.js`, `.py`, `.svelte`, `.astro` 소스는 위처럼 rule 을 더해야 diff 만으로 도메인이 잡힌다. rule 이 없어도 `new --domains` 로 선언한 도메인은 유지된다.
- `protected_changes` 값은 `risk.protected_rules` 의 키여야 한다. 공개 API·웹훅 계약의 실제 위치에는 `public_api_contract`/`webhook_contract` rule 을 둔다.
- `pipeline.config.yaml` 자체가 rule 대상이다(`infrastructure` + `core_architecture`, T3). `ready: true` 이후의 편집은 T3 task(PLAN, EXEC_PLAN, ACCEPTED ADR, 사용자 승인)로 진행하고, 편집하면 prepare 된 모든 task 의 fingerprint 가 stale 이 되어 `revise` 가 필요하다. 실패하는 구현을 통과시키려고 requirements·`test_report` 한도·rule 을 낮추지 않는다.
