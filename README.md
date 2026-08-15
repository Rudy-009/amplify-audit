# amplify-audit

A Claude Code skill that audits your own prompts — **Amplify**, **Cognitive Offload**, or **Bypass** — and reports what you actually kept.

## What it does

하루 동안 Claude에게 보낸 프롬프트를 수집해서, 각각을 분류합니다:

| Verdict | 의미 |
|---------|------|
| **Amplify** | 내가 주도하며 AI를 활용함 (steer / ground / deepen / expand) |
| **Offload** | 인지 부담을 합리적으로 위임함 |
| **Bypass** | 판단·검증·역량 형성을 건너뜀 |

결과는 비율 + 타임라인 + 태그별 분류를 담은 HTML 리포트로 출력됩니다.

<!-- TODO: 스크린샷 — HTML 리포트 예시 -->

## Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Rudy-009/amplify-audit/main/install.sh)
```

설치 스크립트가 자동으로 환경을 감지합니다:
- `claude` CLI가 있으면 → `~/.claude/skills/amplify-audit/`
- `codex` CLI가 있으면 → `~/.agents/skills/amplify-audit/`
- 둘 다 없으면 → 양쪽 모두 설치

### Manual Install (Codex)

```bash
mkdir -p ~/.agents/skills/amplify-audit/agents
curl -fsSL https://raw.githubusercontent.com/Rudy-009/amplify-audit/main/skills/amplify-audit/SKILL.md \
  -o ~/.agents/skills/amplify-audit/SKILL.md
curl -fsSL https://raw.githubusercontent.com/Rudy-009/amplify-audit/main/skills/amplify-audit/audit.py \
  -o ~/.agents/skills/amplify-audit/audit.py
curl -fsSL https://raw.githubusercontent.com/Rudy-009/amplify-audit/main/skills/amplify-audit/agents/openai.yaml \
  -o ~/.agents/skills/amplify-audit/agents/openai.yaml
```

## Usage

Claude Code에서 아래처럼 말하면 됩니다:

```
오늘 프롬프트 분석해줘
```

기타 트리거:
- "내가 AI 제대로 쓴 건지 봐줘"
- "amplify bypass 비율"
- "프롬프트 회고"

### Options

| 옵션 | 설명 | 예시 |
|------|------|------|
| `--since` | 기간 지정 | `--since 7d` |
| `--date` | 특정 날짜 | `--date 2026-08-13` |
| `--session` | 세션 범위 | `--session current` |
| `--project` | 프로젝트 필터 | `--project Heatmap` |

<!-- TODO: 스크린샷 — collect 출력 예시 -->

## How it works

1. **Collect** — `~/.claude/projects/**/*.jsonl`에서 사용자 프롬프트만 추출
2. **Classify** — Claude가 각 프롬프트를 Amplify / Offload / Bypass / Neutral / Ambiguous로 판정
3. **Render** — 판정 결과를 HTML 리포트로 생성 (`~/amplify-audit/2026-08-13.html`)

<!-- TODO: 스크린샷 — 최종 HTML 리포트 전체 모습 -->

## Classification Detail

### Amplify tags
- `steer` — 제약 조건을 명시하며 이끔
- `ground` — 이해를 목적으로 질문함
- `deepen` — 본인이 먼저 산출하고 AI가 반응
- `expand` — 자각하며 영역을 넓힘

### Bypass tags
- `ceded_decisions` — "알아서 해줘" 류, 기준 없이 판단을 넘김
- `skipped_verification` — 결과를 검증 없이 수용
- `illusion_of_competence` — 이해했다는 착각
- `capability_not_formed` — 통째로 위임, 남는 역량 없음

### Cognitive Offload gates
위임 형태의 프롬프트는 3개 gate를 통과해야 합니다:
1. **상황 이해** — 결과를 이해 가능한 형태로 받았는가
2. **여력 확보** — 인지 부담이 실제로 줄었는가
3. **위임 적격** — 이 작업이 내 역량이 될 것은 아닌가

## Requirements

- Claude Code (Claude Desktop이 아님)
- Python 3.8+
- 표준 라이브러리만 사용 (외부 의존성 없음)

## License

MIT

---

## To-Do (배포 준비)

- [x] install.sh 작성
- [x] README.md 보강
- [ ] 스크린샷 추가: HTML 리포트 예시
- [ ] 스크린샷 추가: collect 출력 예시
- [ ] 스크린샷 추가: 최종 HTML 리포트 전체 모습
- [ ] GitHub Release 또는 태그 생성 (v0.1.0)
- [ ] (선택) 데모 GIF 녹화
