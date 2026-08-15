---

## name: amplify-audit description: Audit the user's own prompts from coding agent transcripts (Claude Code or Codex) and classify each as Amplify (Steer / Ground / Deepen / Expand), Cognitive Offload (judged against the 상황 이해 / 여력 확보 / 위임 적격 gates), or Bypass (Ceded Decisions / Skipped Verification / Illusion of Competence / Capability Not Formed), then write an HTML report with the ratio, a debt list with concrete repayment actions, and rewritten versions of the worst prompts. Use when the user says "오늘 프롬프트 분석해줘", "내가 AI 제대로 쓴 건지 봐줘", "amplify bypass 비율", "프롬프트 회고", or asks to review or grade how they have been prompting. Also offer it when they say they feel like they were just copy-pasting AI output without understanding it. Not for reviewing code, PRs, or anyone else's prompts.

---
# Amplify Audit

Two bash calls. Collect prints the prompts to stdout *and* saves them; render reads those saved prompts and takes only your judgements on stdin, joined by `id`. Classification happens in between, by you. Never re-type the prompt text — the transcript's copy is authoritative and yours would only introduce drift.

## 1. Collect

```bash
python3 "$(find ~/.claude/skills ~/.agents/skills -name audit.py -path '*/amplify-audit/*' 2>/dev/null | head -1)" collect

```

Prints the prompts and writes them to `~/amplify-audit/prompts.json` for step 4.

Defaults to today across all projects. Other scopes: `--since 7d`, `--date 2026-08-13`, `--session current`, `--project Heatmap`. Reads `~/.claude/projects/**/*.jsonl` (Claude Code) and `~/.codex/sessions/**/*.jsonl` (Codex) simultaneously. Drops tool results, meta entries, subagent turns, and built-in slash commands.

Under ~8 prompts there isn't enough for a ratio — say so and skip the percentage, but still tag each prompt.

## 2. Classify

One verdict per prompt, decided in this order.

### Is it a delegation of cognitive work?

기억 · 검색 · 정리 · 반복 — work handed to the tool to free up capacity. If yes, it's **Cognitive Offloading** and gets judged at three gates. If no, skip to Amplify/Bypass.


| gate               | 질문                     | 실패하면                                          |
| ------------------ | ---------------------- | --------------------------------------------- |
| `understood` 상황 이해 | 결과를 이해 가능한 형태로 받았는가    | → `bypass` / `illusion_of_competence`         |
| `relieved` 여력 확보   | 인지 부담이 정말 감소했는가        | offload로 두되 비효율로 기록 (검증이 더 오래 걸렸다면 위임한 게 아니다) |
| `eligible` 위임 적격   | 이 반복이 내 역량이 될 것은 아니었는가 | → `bypass` / `capability_not_formed`          |


All three pass → `verdict: "offload"`, `tag: "offload"`. **This is a good outcome, not a lesser Amplify.** CI yaml, 반복 설정, 회의록 정리를 넘기는 건 정확한 판단입니다. Say so.

Never put gates on an `ambiguous` prompt — if the intent didn't resolve, 위임 적격 didn't resolve either. Record the gates on every offload-shaped prompt including the ones that fail into bypass — `"gates": {"understood": false, "relieved": true, "eligible": false}` — so each prompt row can show which gate leaked. Use `null` for a gate you can't judge.

### Otherwise: Amplify or Bypass

**Amplify**


| tag      | 뜻          | tell                                                                             |
| -------- | ---------- | -------------------------------------------------------------------------------- |
| `steer`  | 통제하며 이끌기   | He names the constraint. Contains a decision only he could make.                 |
| `ground` | 모르는 걸 파악하기 | Deliverable is understanding, not an artifact. Often carries his own hypothesis. |
| `deepen` | 오래 남게 연습   | He produces first, AI reacts. Output direction reversed.                         |
| `expand` | 가능성 넓히기    | Stretch with awareness — "지금 실력으로 될지 모르겠는데".                                     |


**Bypass**


| tag                      | 뜻           | tell                                                                   |
| ------------------------ | ----------- | ---------------------------------------------------------------------- |
| `ceded_decisions`        | 판단권을 넘김     | "알아서", "제일 좋은" with no criteria attached.                              |
| `skipped_verification`   | 검증을 생략      | No gap between receiving output and moving on. Read the *next* prompt. |
| `illusion_of_competence` | 이해했다는 착각    | Concept re-asked with no attempt to produce it himself.                |
| `capability_not_formed`  | 역량이 형성되지 않음 | Whole unit of work delegated; nothing transferable left.               |


`neutral` / tag `none` for mechanical requests, continuations, tool operation. Don't force these into a bucket — a report where every prompt is morally significant is one he'll stop trusting.

### Ambiguous — 판정이 성립하지 않은 경우

`verdict: "ambiguous"` when the text genuinely won't resolve. This is a *fifth verdict*, not a weak Amplify and not a confidence score on one — it says the judgement never formed, so the prompt leaves every count: the ratio, the tag donuts, the gates. An `ambiguous` is more useful than a confident wrong tag.

Optionally keep `tag` as the lean ("bypass 쪽으로 기울지만 확정 못 함"); the report renders it muted. Drop `tag` entirely when there isn't even a lean.

Every `ambiguous` needs an `ambiguity`, because the two kinds mean opposite things:


| `ambiguity` | 뜻                                                | 이건 누구 문제인가                             |
| ----------- | ------------------------------------------------ | -------------------------------------- |
| `context`   | 판정 근거가 이 프롬프트 *밖에* 있다 — 앞 턴, 잘린 뒷부분, 그가 이미 읽은 로그 | 도구의 한계. collect가 사용자 발화만 뽑아오니 안 보이는 것. |
| `prompt`    | 맥락을 다 봐도 뭘 하려는 건지 안 잡힌다                          | 발견 대상. 덜 여문 질문을 보냈다는 신호이므로 세어서 보여준다.   |


Default to `context` when torn. `prompt` is a finding about him and shouldn't be asserted on a hunch — a miscounted `context` costs nothing, a miscounted `prompt` manufactures a problem he doesn't have.

If `context` dominates the day, say so in `meta.headline`: that's the tool failing to show enough, not him prompting badly, and the fix is a wider `--since` or a session scope, not a lecture.

Judge the prompt, not the outcome, and quote the deciding evidence in `reason`: "'알아서'만 있고 제약 조건이 하나도 없음" beats "판단 근거가 부족함". Infer his growth zone from the day's topics and use it to judge the 위임 적격 gate; it isn't a field, it's just how you decide.

## 3. Render

```bash
python3 "$(find ~/.claude/skills ~/.agents/skills -name audit.py -path '*/amplify-audit/*' 2>/dev/null | head -1)" render --out ~/amplify-audit/2026-08-13.html <<'JSON'
{ ... }
JSON

```

Reads the text from `--prompts` (default `~/amplify-audit/prompts.json`). Warnings on stderr name any id you left unjudged, invented, or repeated — an unjudged prompt is rendered Neutral, so fix it and re-run rather than shipping a silent downgrade.

Schema — `meta` with `label` only (e.g. `"2026-08-13 · 하루"`), and `classifications[]` with `id` plus `verdict` (`amplify`|`offload`|`bypass`|`neutral`|`ambiguous`) `tag` `gates` `ambiguity` (`context`|`prompt`, required whenever `verdict` is `ambiguous`) `reason` — **id and judgement only, no** `text`.

Nothing else is rendered. Don't send `headline`, `reinvestment`, `rewrites`, `debts`, or `tomorrow` — the report is the ratio, the timeline, and the tagged prompts, and it's his to read. Then in chat: the ratio in one line and the path, nothing more.

## Tone

He asked to be measured, so measure. Don't soften a bypass into "이것도 나름 전략적이었네요", and don't inflate the amplify count to be encouraging — a flattering audit is a useless one. Equally, don't moralize: this is a ledger, not a confession. Legitimate offloading should be stated as legitimate without hedging. The report shows the shape of the day and stops there — resist adding advice, plans, or homework that he didn't ask for.