# amplify-audit (archive)

Prompt self-audit: classifies each prompt as Amplify / Offload / Bypass, generates an HTML report.

## Entry Point
`scripts/audit.py` — two subcommands: `collect` and `render`.

## Pipeline
1. **collect** → extracts user prompts from `~/.claude/projects/**/*.jsonl` and `~/.codex/sessions/**/*.jsonl`, outputs JSON
2. **classify** → Claude judges each prompt (verdict + tag + gates + confidence + reason)
3. **render** → reads classifications from stdin + prompts file, writes HTML report

## Report Sections
- **chips** — unit, prompt count, growth zones, projects
- **headline** — one-sentence summary from meta
- **요약** — main donut (Amplify %), legend, amp/bypass mini donuts
- **위임 관문** — 3 offload gates (understood / relieved / eligible) with bars
- **reinvestment** — whether saved cognitive load was reinvested (spent/leaked)
- **하루의 흐름** — timeline bar chart colored by tag
- **부채 원장** — bypass debts with time estimates and actions
- **고쳐 쓴 프롬프트** — rewrites with before/after and copy button
- **내일의 한 가지** — tomorrow trigger + detail
- **전체 프롬프트** — filterable list with gate pills, confidence markers

## Collect Options
`--root` `--codex-root` `--date` `--since` `--session` `--project` `--max-chars` `--out`

## Render Options
`--out` `--prompts`

## Classification Schema
Tags: steer, ground, deepen, expand (Amplify) | offload (Offload) | ceded_decisions, skipped_verification, illusion_of_competence, capability_not_formed (Bypass) | none (Neutral)

Offload gates: understood, relieved, eligible (bool each)

Confidence: high | low (low → 판단 보류 pill, excluded from scored ratios)
