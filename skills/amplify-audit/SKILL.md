---
name: amplify-audit
description: Audit the user's own prompts — classify as Amplify, Offload, or Bypass and generate an HTML report. Trigger on "프롬프트 분석", "amplify bypass 비율", "프롬프트 회고", or requests to review prompting quality.
---
# Amplify Audit

Two bash calls. Classification happens in between, by you. Never re-type prompt text — the transcript copy is authoritative.

```bash
AUDIT="$(find ~/.claude/skills ~/.agents/skills -name audit.py -path '*/amplify-audit/*' 2>/dev/null | head -1)"
```

## 1. Collect

```bash
python3 "$AUDIT" collect
```

Writes `~/amplify-audit/prompts.json`. Reads `~/.claude/projects/**/*.jsonl` + `~/.codex/sessions/**/*.jsonl`. Options: `--since 7d`, `--date 2026-08-13`, `--session current`, `--project Heatmap`.

Under ~8 prompts skip percentages, still tag each.

## 2. Classify

One verdict per prompt.

### Offload check (first)

If the prompt delegates cognitive work (memory, search, formatting, repetition), judge 3 gates:

| gate | question | fail → |
|------|----------|--------|
| `understood` | 결과를 이해 가능한 형태로 받았는가 | `bypass`/`illusion_of_competence` |
| `relieved` | 인지 부담이 실제로 줄었는가 | mark inefficient |
| `eligible` | 이 작업이 내 역량이 될 것은 아닌가 | `bypass`/`capability_not_formed` |

All pass → `verdict:"offload"`, `tag:"offload"`. This is a good outcome. Record gates on every offload-shaped prompt including failures: `"gates":{"understood":false,"relieved":true,"eligible":false}`. Use `null` for unjudgeable gates. Never gate an `ambiguous` prompt.

### Amplify

| tag | tell |
|-----|------|
| `steer` | Names a constraint. Contains a decision only he could make. |
| `ground` | Deliverable is understanding. Often carries his own hypothesis. |
| `deepen` | He produces first, AI reacts. |
| `expand` | Stretch with awareness — "지금 실력으로 될지 모르겠는데". |

### Bypass

| tag | tell |
|-----|------|
| `ceded_decisions` | "알아서", "제일 좋은" with no criteria. |
| `skipped_verification` | No gap between receiving output and moving on. |
| `illusion_of_competence` | Concept re-asked with no attempt to produce it himself. |
| `capability_not_formed` | Whole unit delegated; nothing transferable left. |

### Neutral

`verdict:"neutral"`, `tag:"none"` for mechanical requests and continuations. Don't force these into a bucket.

### Ambiguous

`verdict:"ambiguous"` when judgement doesn't form. Requires `ambiguity`:
- `context` — evidence is outside this prompt (default when torn)
- `prompt` — prompt itself is unclear (a finding; assert only with confidence)

Quote deciding evidence in `reason`.

## 3. Render

```bash
python3 "$AUDIT" render --out ~/amplify-audit/2026-08-13.html <<'JSON'
{"meta":{"label":"2026-08-13 · Today"},"classifications":[{"id":"p001","verdict":"amplify","tag":"steer","reason":"..."},…]}
JSON
```

Schema: `meta.label` + `classifications[]` with `id`, `verdict`, `tag`, `gates`, `ambiguity`, `reason`. No `text` — render reads it from prompts.json.

Output in chat: ratio in one line + file path. Nothing more.

## Tone

Measure, don't soften or moralize. A flattering audit is useless; a moralizing one gets ignored.
