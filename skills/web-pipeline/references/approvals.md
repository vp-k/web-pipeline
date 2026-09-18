# 승인: 사용자의 결정을 기록할 뿐, 대신 결정하지 않는다

먼저 프로젝트의 `approval_policy`를 확인한다(`python -m web_pipeline status`).

| 정책 | 보호되지 않은 T0–T2 | 보호 변경·T3/T4·예외·Release |
| --- | --- | --- |
| `standard` (새 도입 기본값) | 사용자 승인 게이트 없음. T1/T2는 로컬 리뷰(`review`) | 대화에서 받은 사용자 승인을 **영수증**으로 기록. 이름·신원·공개키·trust 파일 불필요 |
| `strict` 또는 필드 없음 | 서명된 사람 승인 | 외부 trust 파일로 검증되는 실제 서명 |

자세한 규칙은 프로젝트의 `Docs/Runbooks/APPROVALS.md`.

## 절차 (standard)

1. **먼저 물어보지 말고 확인한다.**
   `python -m web_pipeline approval-request --task <TaskId> --phase design|review|release|exception [--check-id <id>]`
   - `NO_APPROVAL_REQUIRED`, `SATISFIED` → 묻지 않고 계속한다. 영수증도 전이도 생기지 않는다.
   - `AWAITING_USER` → 실제로 빠졌거나 무효인 승인 사유가 들어 있다.
2. **기술적 선행 조건을 먼저 해결한다.** 실패한 check를 둔 채 허락부터 구하지 않는다.
3. **한 번에 묶어 묻는다.** 그 단계에 필요한 책임을 모두 한 질문에 담는다. 역할별·단계별로 쪼개 묻지 않는다. 구체적인 범위, 책임, 위험, 조건, 리비전/핑거프린트, 제외 사항을 보여 준다. review/release는 묶인 Full 증거도 보여 준다. 응답을 기다리는 동안 반환된 요청 JSON을 바꾸지 않는다.
4. **명확한 승인을 받은 뒤** 요청 JSON에 `outcome: "APPROVED"`, 실제 `user_message`, 실제 `presented_scope`, 사실대로의 `source_reference`를 더해 `Docs/Work/<TaskId>/` 아래에 저장하고:
   `python -m web_pipeline approve --task <TaskId> --record <파일>`
   그 다음 평소대로 재검증·전이한다.
5. 큐가 승인 대기로 멈춰 있었다면 `loop retry --task <TaskId> --reason "..."` 후 `loop next`.

## 승인으로 취급하지 않는 것

- 예전의 포괄적인 "계속해", 거절, 인용문, 어시스턴트 자신의 말, 도구 출력.
- 리비전·범위·증거가 바뀐 뒤 새로 만든 요청에 옛 메시지를 옮겨 붙이는 것.
- 침묵. 맥락이 빠졌거나 모호하면 범위를 특정한 짧은 질문 하나를 한다. 신원이나 trust를 요구하지 않는다.

이미 화면에 보인 승인은, 보여 준 범위와 요청 바인딩이 그대로이고 답이 분명할 때만 다시 묻지 않고 기록할 수 있다.

## 경계

- 옮겨 적는 것은 허용된다. 보호된 결정을 내리는 것은 허용되지 않는다. 영수증은 한 사용자의 결정일 뿐 인증된 역할이나 독립된 사람 리뷰가 아니다. 여러 책임을 채우려고 사람을 지어내지 않는다.
- 설계 승인 ≠ 리뷰 승인 ≠ Release 승인 ≠ 예외 승인. 조건부 승인은 실제 PASS 증거로 조건을 충족한 뒤 기록한다. 예외는 정확한 check ID와 승인된 사유가 필요하다.
- 승인이 철회되면 멈추고 사유와 함께 `revise`한다. 옛 증거는 보존한다.
- AI 리뷰(`pipeline-reviewer`, `review`)는 자문 증거다. 사용자의 수락과 별개다.
- Release는 **비운영 준비 상태 검증**이다. 운영 배포, 운영 데이터 변경, 파괴적 마이그레이션, 비밀 교체는 별도의 명시적 실행 요청과 실제 외부 권한이 필요하다. 영수증도 이 플러그인도 그 권한을 주지 않는다.

## standard 프로젝트에 기존 서명 기록이 있을 때

서명된 승인·예외 증거가 이미 있는 작업은 평소 게이트와 같은 외부 trust 파일을 `approval-request --trust <경로>`와 `approve --trust <경로>`에 넘기거나 `WEB_PIPELINE_TRUST` 환경 변수를 쓴다. 사용자 영수증 자체에는 trust가 필요 없다. 실제 작업을 위해 trust 저장소를 새로 만들거나 테스트 키를 넣지 않는다.
