#!/usr/bin/env python3
"""amplify-audit — two subcommands.

  collect : read Claude Code transcripts, print the user's prompts as JSON
            and save them to --out (default ~/amplify-audit/prompts.json)
  render  : read the saved prompts from --prompts and the classifications
            from stdin, join them by id, write the HTML report

The prompt text is written once by collect and never re-sent: stdin carries
only ids plus judgements, so the report can't drift from the transcript.

Stdlib only.
"""

from __future__ import annotations

import argparse
import html
import math
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from string import Template

# ---------------------------------------------------------------- collect

NOISE_PREFIXES = ("<local-command-stdout>", "<system-reminder>",
                  "Caveat: The messages below were generated", "[Request interrupted",
                  "API Error", "This session is being continued from a previous")
NOISE_EXACT = {"continue", "계속", "ㄱ", "y", "yes", "ok", "네", "응", "no", "n"}
BUILTIN_CMDS = {"clear", "compact", "config", "context", "cost", "doctor", "exit",
                "export", "help", "hooks", "ide", "init", "login", "logout", "mcp",
                "memory", "model", "permissions", "resume", "rewind", "status",
                "statusline", "terminal-setup", "todos", "upgrade", "usage", "vim",
                "agents", "output-style", "privacy-settings"}
CMD_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.S)
CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def local_ts(raw: str):
    try:
        dt = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone()


def text_of(content):
    """Return (text, is_tool_result)."""
    if isinstance(content, str):
        return content, False
    if not isinstance(content, list):
        return "", False
    parts, tr = [], False
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_result":
            tr = True
        elif b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif b.get("type") == "image":
            parts.append("[image]")
    return "\n".join(p for p in parts if p), tr


def collect(args) -> None:
    root = Path(args.root).expanduser()
    if not root.exists():
        sys.exit(f"transcripts not found: {root}  (pass --root if yours differs)")

    now = datetime.now().astimezone()
    if args.date:
        start = datetime.fromisoformat(args.date).replace(tzinfo=now.tzinfo)
        start, end = start, start + timedelta(days=1)
    elif args.since:
        m = re.fullmatch(r"(\d+)([dh])", args.since)
        if not m:
            sys.exit("--since looks like 7d or 12h")
        step = timedelta(days=int(m[1])) if m[2] == "d" else timedelta(hours=int(m[1]))
        start, end = now - step, now
    elif args.session or args.project:
        start = end = None
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

    session = args.session
    if session == "current":
        files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        session = files[0].stem if files else sys.exit(f"no sessions under {root}")

    out, skipped = [], Counter()
    for f in sorted(root.rglob("*.jsonl")):
        if session and f.stem != session:
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") != "user" or r.get("isMeta") or r.get("isSidechain"):
                skipped["not_user"] += 1
                continue

            txt, tool_result = text_of((r.get("message") or {}).get("content"))
            if tool_result:
                skipped["tool_result"] += 1
                continue

            cwd = r.get("cwd", "")
            if args.project and args.project.lower() not in cwd.lower():
                continue
            ts = local_ts(r.get("timestamp", ""))
            if start and ts and not (start <= ts < end):
                skipped["out_of_range"] += 1
                continue

            txt = txt.strip()
            slash = "<command-name>" in txt
            if slash:
                name = CMD_NAME.search(txt)
                a = CMD_ARGS.search(txt)
                txt = " ".join(x for x in [name and name[1].strip(),
                                           a and a[1].strip()] if x).strip()
                if txt.split(" ")[0].lstrip("/").lower() in BUILTIN_CMDS:
                    skipped["noise"] += 1
                    continue
            txt = re.sub(r"<system-reminder>.*?</system-reminder>", "", txt, flags=re.S).strip()

            if (not txt or txt.startswith(NOISE_PREFIXES)
                    or txt.lower() in NOISE_EXACT or len(txt) < 2):
                skipped["noise"] += 1
                continue

            cut = len(txt) > args.max_chars
            out.append({"ts": ts.isoformat() if ts else "",
                        "project": Path(cwd).name if cwd else f.parent.name,
                        "text": txt[:args.max_chars] + (" …[truncated]" if cut else "")})

    out.sort(key=lambda p: p["ts"])
    deduped = []
    for p in out:  # drop resends
        if deduped and deduped[-1]["text"] == p["text"]:
            continue
        deduped.append(p)
    for i, p in enumerate(deduped, 1):
        p["id"] = f"p{i:03d}"

    payload = {"count": len(deduped), "skipped": dict(skipped), "prompts": deduped}
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(blob, encoding="utf-8")

    print(blob)
    print(f"{len(deduped)} prompts -> {out}", file=sys.stderr)
    if not deduped:
        print("no prompts matched — try a wider --since or check --root", file=sys.stderr)


# ---------------------------------------------------------------- render

LABELS = {
    "steer": ("Steer", "통제하며 이끌기"), "ground": ("Ground", "모르는 걸 파악하기"),
    "deepen": ("Deepen", "오래 남게 연습"), "expand": ("Expand", "가능성 넓히기"),
    "offload": ("Offload", "인지 작업 위임"),
    "ceded_decisions": ("Ceded Decisions", "판단권을 넘김"),
    "skipped_verification": ("Skipped Verification", "검증을 생략"),
    "illusion_of_competence": ("Illusion of Competence", "이해했다는 착각"),
    "capability_not_formed": ("Capability Not Formed", "역량이 형성되지 않음"),
    "none": ("Neutral", "기계적 요청"),
}
AMP = ["steer", "ground", "deepen", "expand"]
BYP = ["ceded_decisions", "skipped_verification", "illusion_of_competence",
       "capability_not_formed"]
GATES = [("understood", "상황 이해", "결과를 이해 가능한 형태로 받았는가"),
         ("relieved", "여력 확보", "인지 부담이 정말 감소했는가"),
         ("eligible", "위임 적격", "반복이 내 역량이 될 것은 아니었는가")]

TAG_VAR = {
    "steer": "--blue", "ground": "--teal", "deepen": "--indigo", "expand": "--mint",
    "offload": "--yellow",
    "ceded_decisions": "--orange", "skipped_verification": "--red",
    "illusion_of_competence": "--pink", "capability_not_formed": "--purple",
    "none": "--gray",
}

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
 --blue:#007AFF;--green:#34C759;--indigo:#5856D6;--orange:#FF9500;--pink:#FF2D55;
 --purple:#AF52DE;--red:#FF3B30;--teal:#30B0C7;--mint:#00C7BE;--yellow:#E6B400;
 --gray:#8E8E93;--gray3:#C7C7CC;--gray5:#E5E5EA;
 --bg:#F2F2F7;--card:#FFFFFF;--label:#000000;--label2:rgba(60,60,67,.6);
 --label3:rgba(60,60,67,.3);--sep:rgba(60,60,67,.29);--fill:rgba(120,120,128,.12);
 --radius:12px;
 --sf:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Helvetica Neue",
   "Apple SD Gothic Neo","Pretendard Variable",Pretendard,sans-serif}
@media (prefers-color-scheme:dark){:root{
 --blue:#0A84FF;--green:#30D158;--indigo:#5E5CE6;--orange:#FF9F0A;--pink:#FF375F;
 --purple:#BF5AF2;--red:#FF453A;--teal:#40C8E0;--mint:#66D4CF;--yellow:#FFD60A;
 --gray:#8E8E93;--gray3:#48484A;--gray5:#2C2C2E;
 --bg:#000000;--card:#1C1C1E;--label:#FFFFFF;--label2:rgba(235,235,245,.6);
 --label3:rgba(235,235,245,.3);--sep:rgba(84,84,88,.65);--fill:rgba(120,120,128,.24)}}
body{margin:0;background:var(--bg);color:var(--label);font-family:var(--sf);
 font-size:17px;line-height:1.47;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:44px 20px 80px}
h1{font-size:34px;font-weight:700;letter-spacing:.37px;margin:0}
h2{font-size:13px;font-weight:400;letter-spacing:.06em;text-transform:uppercase;
 color:var(--label2);margin:34px 0 8px;padding:0 16px}
h3{font-size:17px;font-weight:600;margin:0;letter-spacing:-.4px}
.sub{color:var(--label2);font-size:15px;margin:4px 0 0}
.head{padding:0 4px 6px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.chip{background:var(--fill);color:var(--label2);font-size:12px;padding:3px 9px;
 border-radius:999px}
.headline{background:var(--card);border-radius:var(--radius);padding:16px;margin-top:16px;
 font-size:16px;line-height:1.5}
.card{background:var(--card);border-radius:var(--radius);overflow:hidden}
.row{padding:12px 16px;border-top:.5px solid var(--sep)}
.row:first-child{border-top:0}

.donut-main{display:flex;align-items:center;gap:24px;padding:20px 16px;flex-wrap:wrap}
.dw{position:relative;flex:0 0 auto;line-height:0}
.dw .mid{position:absolute;inset:0;display:flex;flex-direction:column;
 align-items:center;justify-content:center;text-align:center;line-height:1.2}
.dw .mid b{font-size:30px;font-weight:700;letter-spacing:-.5px;line-height:1}
.dw .mid span{font-size:11px;color:var(--label2);margin-top:2px}
.legend{flex:1 1 200px;min-width:190px}
.lg{display:flex;align-items:center;gap:10px;padding:7px 0;font-size:15px}
.lg .dot{width:11px;height:11px;border-radius:50%;flex:0 0 auto}
.lg .nm{flex:1}
.lg .vl{font-variant-numeric:tabular-nums;color:var(--label2)}
.lg.sep{border-top:.5px solid var(--sep);margin-top:6px}
.pair{display:grid;grid-template-columns:1fr 1fr;border-top:.5px solid var(--sep)}
.pair>div{padding:18px 16px}
.pair>div+div{border-left:.5px solid var(--sep)}
.pair h4{margin:0 0 12px;font-size:13px;font-weight:600;color:var(--label2);
 display:flex;align-items:center;gap:7px}
.pair h4 i{width:8px;height:8px;border-radius:50%;display:inline-block}
.mini{display:flex;align-items:center;gap:14px}
.mini .keys{flex:1;min-width:0}
.mini .k{display:flex;align-items:center;gap:7px;font-size:12.5px;padding:2.5px 0;
 color:var(--label2)}
.mini .k i{width:8px;height:8px;border-radius:2px;flex:0 0 auto}
.mini .k b{color:var(--label);font-weight:600;font-variant-numeric:tabular-nums;
 margin-left:auto;padding-left:8px}

.gates{display:grid;grid-template-columns:repeat(3,1fr)}
.gates>div{padding:16px;text-align:center}
.gates>div+div{border-left:.5px solid var(--sep)}
.gates .gname{font-size:13px;font-weight:600}
.gates .gq{font-size:11px;color:var(--label3);margin-top:3px;line-height:1.35}
.gates .gbar{height:6px;border-radius:3px;background:var(--fill);margin:10px 0 6px;
 overflow:hidden}
.gates .gbar i{display:block;height:100%;border-radius:3px;background:var(--yellow)}
.gates .gval{font-size:13px;color:var(--label2);font-variant-numeric:tabular-nums}
.gates .gval b{color:var(--label);font-weight:600}
.reinvest{padding:18px 16px;border-top:.5px solid var(--sep)}
.reinvest .st{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
 border-radius:999px;padding:3px 10px;background:var(--fill)}
.reinvest p{margin:11px 0 0;font-size:17px;font-weight:600;letter-spacing:-.3px;line-height:1.4}
.reinvest .d{margin-top:8px;font-size:14.5px;color:var(--label2);line-height:1.5}

.strip{padding:18px 16px 12px}
.bars{display:flex;align-items:flex-end;gap:2px;height:92px}
.bars button{flex:1 1 4px;min-width:3px;border:0;padding:0;border-radius:2.5px;
 cursor:pointer;opacity:.92;transition:opacity .15s,transform .15s;transform-origin:bottom}
.bars button:hover,.bars button:focus-visible{opacity:1;transform:scaleX(1.6)}
.axis{display:flex;justify-content:space-between;font-size:11px;color:var(--label3);
 margin-top:8px;border-top:.5px solid var(--sep);padding-top:7px}

.debt{padding:14px 16px;border-top:.5px solid var(--sep)}
.debt:first-child{border-top:0}
.debt .t{display:flex;gap:10px;align-items:baseline}
.debt .t h3{flex:1;font-size:16px}
.debt .mins{font-size:13px;color:var(--label2);font-variant-numeric:tabular-nums;
 background:var(--fill);border-radius:999px;padding:2px 9px;white-space:nowrap}
.debt .act{margin-top:7px;font-size:15px;line-height:1.45}
.debt .meta{margin-top:7px;font-size:12px;color:var(--label3)}
.debt .meta a{color:var(--blue);text-decoration:none}
.sum{padding:12px 16px;border-top:.5px solid var(--sep);display:flex;
 justify-content:space-between;font-size:13px;color:var(--label2)}

.rw{margin-top:10px}
.rw .lab{font-size:12px;color:var(--label2);margin-bottom:5px;display:flex;
 align-items:center;gap:8px}
.rw .lab a{color:var(--blue);text-decoration:none}
.before{color:var(--label2);text-decoration:line-through;font-size:15px}
.after{font-size:16px;line-height:1.5}
.why{font-size:13.5px;color:var(--label2)}
.copy{margin-left:auto;font:inherit;font-size:12px;background:var(--fill);border:0;
 color:var(--blue);padding:3px 11px;border-radius:999px;cursor:pointer}
.copy:active{opacity:.6}

.tmr{background:var(--card);border-radius:var(--radius);padding:20px 16px;
 border-left:4px solid var(--blue)}
.tmr .kicker{font-size:12px;color:var(--blue);font-weight:600;letter-spacing:.04em;
 text-transform:uppercase}
.tmr p{font-size:20px;font-weight:600;letter-spacing:-.4px;line-height:1.35;margin:8px 0 0}
.tmr .d{font-size:14px;color:var(--label2);margin-top:10px}

.seg{display:flex;background:var(--fill);border-radius:9px;padding:2px;margin:0 0 10px}
.seg button{flex:1;font:inherit;font-size:13px;font-weight:500;border:0;background:none;
 color:var(--label);padding:6px 4px;border-radius:7px;cursor:pointer;white-space:nowrap}
.seg button[aria-pressed="true"]{background:var(--card);box-shadow:0 1px 3px rgba(0,0,0,.1)}
.p{padding:13px 16px;border-top:.5px solid var(--sep);border-left:3px solid transparent}
.p:first-child{border-top:0}
.p.amplify{border-left-color:var(--green)}
.p.offload{border-left-color:var(--yellow)}
.p.bypass{border-left-color:var(--orange)}
.p .top{display:flex;flex-wrap:wrap;gap:4px 9px;align-items:center;font-size:12px;
 color:var(--label3)}
.p .tag{font-weight:600}
.p .pill{background:var(--fill);color:var(--label2);border-radius:999px;padding:1px 8px;
 font-size:11px}
.p .gate{border-radius:999px;padding:1px 8px;font-size:11px;font-weight:600}
.p .gate.ok{background:rgba(52,199,89,.15);color:var(--green)}
.p .gate.no{background:rgba(255,59,48,.15);color:var(--red)}
.p .text{margin:6px 0 0;font-size:16px;white-space:pre-wrap;word-break:break-word}
.p .reason{margin:7px 0 0;font-size:13.5px;color:var(--label2);line-height:1.45}
.p:target{background:var(--fill)}
.p.low .text{color:var(--label2)}
.empty{padding:20px 16px;color:var(--label3);font-size:15px}
footer{margin-top:34px;padding:0 16px;font-size:12px;color:var(--label3)}
@media (max-width:520px){.wrap{padding:28px 12px 60px}h1{font-size:28px}
 .pair,.gates{grid-template-columns:1fr}
 .pair>div+div,.gates>div+div{border-left:0;border-top:.5px solid var(--sep)}
 .donut-main{gap:16px}}
@media print{body{background:#fff}.seg,.copy{display:none}.p{break-inside:avoid}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = """
const btns=[...document.querySelectorAll('.seg button')],rows=[...document.querySelectorAll('.p')];
btns.forEach(b=>b.onclick=()=>{btns.forEach(x=>x.setAttribute('aria-pressed',x===b));
const f=b.dataset.f;let n=0;rows.forEach(r=>{const on=f==='all'||r.dataset.v===f;
r.hidden=!on;if(on)n++});document.getElementById('empty').hidden=n>0});
document.querySelectorAll('.bars button').forEach(t=>t.onclick=()=>{btns[0].click();
const e=document.getElementById(t.dataset.id);e.scrollIntoView({behavior:'smooth',block:'center'});
location.hash=t.dataset.id});
document.querySelectorAll('.copy').forEach(b=>b.onclick=async()=>{
try{await navigator.clipboard.writeText(b.dataset.c);const o=b.textContent;b.textContent='복사됨';
setTimeout(()=>b.textContent=o,1400)}catch(e){b.textContent='복사 실패'}});
"""

PAGE = Template("""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>프롬프트 리포트 — $label</title><style>$css</style></head><body><div class="wrap">

<div class="head"><h1>프롬프트 리포트</h1><p class="sub">$label</p>
<div class="chips">$chips</div></div>
<div class="headline">$headline</div>

<h2>요약</h2>
<div class="card">
  <div class="donut-main">$main_donut<div class="legend">$legend</div></div>
  <div class="pair">
    <div><h4><i style="background:var(--green)"></i>Amplify 분류</h4>$amp_mini</div>
    <div><h4><i style="background:var(--orange)"></i>Bypass 분류</h4>$byp_mini</div>
  </div>
</div>

<h2>위임 관문 · Offload $offload_n건</h2>
<div class="card"><div class="gates">$gates</div>
<div class="reinvest">$reinvest</div></div>

<h2>하루의 흐름</h2>
<div class="card strip"><div class="bars">$bars</div>
<div class="axis"><span>$first</span><span>막대 높이 = 프롬프트 길이 · 탭하면 이동</span><span>$last</span></div></div>

<h2>부채 원장</h2>
<div class="card">$debts</div>

$rewrites

<h2>내일의 한 가지</h2>
<div class="tmr"><div class="kicker">Trigger</div><p>$tomorrow</p><div class="d">$detail</div></div>

<h2>전체 프롬프트 · $count</h2>
<div class="seg">$filters</div>
<div class="card">$rows<div class="empty" id="empty" hidden>해당하는 프롬프트가 없습니다.</div></div>

<footer>$generated · amplify-audit · 각 항목의 판단 근거는 함께 적혀 있습니다. 동의하지 않는 태그는 반박 대상입니다.</footer>
</div><script>$js</script></body></html>""")


def esc(s) -> str:
    return html.escape(str(s or ""))


def hhmm(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M")
    except (ValueError, TypeError):
        return "--:--"


def donut(segments, size=148, thickness=20, gap_deg=2.0) -> str:
    """segments: [(value, css_var)] -> SVG donut with small separators."""
    total = sum(v for v, _ in segments)
    if total <= 0:
        return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
                f'<circle cx="{size/2}" cy="{size/2}" r="{(size-thickness)/2}" fill="none" '
                f'stroke="var(--gray5)" stroke-width="{thickness}"/></svg>')
    r = (size - thickness) / 2
    circ = 2 * math.pi * r
    live = [(v, c) for v, c in segments if v > 0]
    gap = (circ * gap_deg / 360) if len(live) > 1 else 0
    parts, off = [], 0.0
    for v, var in live:
        seg = v / total * circ
        draw = max(seg - gap, circ * 0.004)
        parts.append(
            f'<circle cx="{size/2}" cy="{size/2}" r="{r:.2f}" fill="none" '
            f'stroke="var({var})" stroke-width="{thickness}" stroke-linecap="butt" '
            f'stroke-dasharray="{draw:.2f} {circ-draw:.2f}" stroke-dashoffset="{-off:.2f}" '
            f'transform="rotate(-90 {size/2} {size/2})"/>')
        off += seg
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
            f'role="img">{"".join(parts)}</svg>')


JUDGEMENT_FIELDS = ("verdict", "tag", "gates", "confidence", "reason")


def join(prompts, judgements):
    """Attach judgements to prompts by id. Transcript text always wins."""
    by_id, dupes = {}, []
    for j in judgements:
        if not isinstance(j, dict):
            continue
        jid = j.get("id")
        if not jid:
            continue
        (dupes.append(jid) if jid in by_id else None)
        by_id[jid] = j

    merged, unjudged = [], []
    for p in prompts:
        j = by_id.pop(p.get("id"), None)
        if j is None:
            unjudged.append(p.get("id"))
        else:
            p = {**p, **{k: v for k, v in j.items() if k in JUDGEMENT_FIELDS}}
        merged.append(p)

    for label, ids in (("no judgement", unjudged), ("unknown id", list(by_id)),
                       ("duplicate id", dupes)):
        if ids:
            shown = ", ".join(str(i) for i in ids[:8])
            more = f" (+{len(ids) - 8})" if len(ids) > 8 else ""
            print(f"warning: {len(ids)} {label}: {shown}{more}", file=sys.stderr)
    return merged


def render(args) -> None:
    data = json.load(sys.stdin)
    meta = data.get("meta", {})

    src = Path(args.prompts).expanduser()
    if not src.exists():
        sys.exit(f"prompts file not found: {src}  (run collect first, or pass --prompts)")
    prompts = json.loads(src.read_text(encoding="utf-8")).get("prompts", [])

    judgements = data.get("classifications")
    if judgements is None:
        judgements = data.get("prompts", [])
    prompts = join(prompts, judgements)
    scored = [p for p in prompts if p.get("confidence") != "low"]
    v = Counter(p.get("verdict", "neutral") for p in scored)
    amp, off, byp, neu = v["amplify"], v["offload"], v["bypass"], v["neutral"]
    classified = amp + off + byp
    pct = round(amp / classified * 100) if classified else 0

    main = (f'<div class="dw">'
            f'{donut([(amp,"--green"),(off,"--yellow"),(byp,"--orange"),(neu,"--gray3")])}'
            f'<div class="mid"><b>{pct}%</b><span>Amplify</span></div></div>')

    legend = "".join(
        f'<div class="lg"><span class="dot" style="background:var({var})"></span>'
        f'<span class="nm">{nm}</span><span class="vl">{n}</span></div>'
        for nm, n, var in (("Amplify", amp, "--green"), ("Offload", off, "--yellow"),
                           ("Bypass", byp, "--orange"), ("Neutral", neu, "--gray3")))
    legend += (f'<div class="lg sep"><span class="dot" style="background:var(--red)"></span>'
               f'<span class="nm">갚아야 할 부채</span><span class="vl">{byp}</span></div>')

    counts = Counter(p.get("tag", "none") for p in prompts)

    def mini(tags):
        svg = donut([(counts.get(t, 0), TAG_VAR[t]) for t in tags], size=84, thickness=13)
        keys = "".join(
            f'<div class="k"><i style="background:var({TAG_VAR[t]});'
            f'{"opacity:.35" if not counts.get(t) else ""}"></i>{LABELS[t][0]}'
            f'<b>{counts.get(t,0)}</b></div>' for t in tags)
        return f'<div class="mini"><div class="dw">{svg}</div><div class="keys">{keys}</div></div>'

    gated = [p for p in prompts if isinstance(p.get("gates"), dict)]
    gate_html = ""
    for key, name, question in GATES:
        judged = [p for p in gated if p["gates"].get(key) is not None]
        ok = sum(1 for p in judged if p["gates"].get(key))
        w = (ok / len(judged) * 100) if judged else 0
        val = f'<b>{ok}</b>/{len(judged)} 통과' if judged else "판정 없음"
        gate_html += (f'<div><div class="gname">{name}</div><div class="gq">{question}</div>'
                      f'<div class="gbar"><i style="width:{w:.0f}%"></i></div>'
                      f'<div class="gval">{val}</div></div>')

    ri = data.get("reinvestment") or {}
    status = ri.get("status", "unclear")
    ri_color = {"spent": "--green", "leaked": "--orange"}.get(status, "--gray")
    ri_label = {"spent": "재투자됨", "leaked": "새어나감"}.get(status, "판정 불가")
    reinvest = (f'<span class="st" style="color:var({ri_color})">재투자 · {ri_label}</span>'
                f'<p>{esc(ri.get("headline", "확보한 여력의 행방을 판정할 근거가 부족함."))}</p>'
                + (f'<div class="d">{esc(ri.get("detail"))}</div>' if ri.get("detail") else ""))

    lengths = [len(p.get("text", "")) for p in prompts] or [1]
    top = max(max(lengths), 1)
    bars = "".join(
        f'<button data-id="{esc(p.get("id"))}" '
        f'style="height:{14 + 76 * min(1.0, len(p.get("text",""))/top):.0f}px;'
        f'background:var({TAG_VAR.get(p.get("tag","none"),"--gray")})" '
        f'title="{esc(hhmm(p.get("ts","")))} · {esc(LABELS.get(p.get("tag","none"),("",""))[0])} · '
        f'{esc(p.get("text","")[:60])}"></button>' for p in prompts)

    debts = data.get("debts", [])
    if debts:
        mins = sum(int(d.get("minutes") or 0) for d in debts)
        debts_html = "".join(
            f'<div class="debt"><div class="t"><h3>{esc(d.get("title"))}</h3>'
            + (f'<span class="mins">{d["minutes"]}분</span>' if d.get("minutes") else "")
            + f'</div><div class="act">{esc(d.get("action"))}</div>'
            f'<div class="meta">{esc(LABELS.get(d.get("type","none"),("",""))[1])}'
            + (" · " + " ".join(f'<a href="#{esc(r)}">{esc(r)}</a>' for r in d.get("refs", []))
               if d.get("refs") else "")
            + '</div></div>' for d in debts)
        debts_html += f'<div class="sum"><span>합계</span><span>{mins}분</span></div>'
    else:
        debts_html = '<div class="empty">갚아야 할 항목 없음.</div>'

    rws = data.get("rewrites", [])
    rw_html = ('<h2>고쳐 쓴 프롬프트</h2>' + "".join(
        f'<div class="card rw"><div class="row"><div class="lab">보낸 것 '
        f'<a href="#{esc(r.get("ref"))}">{esc(r.get("ref"))}</a></div>'
        f'<div class="before">{esc(r.get("before"))}</div></div>'
        f'<div class="row"><div class="lab">대신 이렇게'
        f'<button class="copy" data-c="{esc(r.get("after"))}">복사</button></div>'
        f'<div class="after">{esc(r.get("after"))}</div></div>'
        f'<div class="row"><div class="why">{esc(r.get("why"))}</div></div></div>'
        for r in rws)) if rws else ""

    def gate_pills(p) -> str:
        g = p.get("gates")
        if not isinstance(g, dict):
            return ""
        out = ""
        for key, name, _ in GATES:
            val = g.get(key)
            if val is None:
                continue
            out += (f'<span class="gate {"ok" if val else "no"}">'
                    f'{"✓" if val else "✗"} {name}</span>')
        return out

    rows = "".join(
        f'<div class="p {esc(p.get("verdict","neutral"))}'
        f'{" low" if p.get("confidence")=="low" else ""}" id="{esc(p.get("id"))}" '
        f'data-v="{esc(p.get("verdict","neutral"))}">'
        f'<div class="top"><span>{hhmm(p.get("ts",""))}</span>'
        f'<span>{esc(p.get("project"))}</span>'
        f'<span class="tag" style="color:var({TAG_VAR.get(p.get("tag","none"),"--gray")})">'
        f'{esc(LABELS.get(p.get("tag","none"),("Neutral",""))[0])}</span>'
        + gate_pills(p)
        + ('<span class="pill">판단 보류</span>' if p.get("confidence") == "low" else "")
        + f'</div><div class="text">{esc(p.get("text"))}</div>'
        + (f'<div class="reason">{esc(p.get("reason"))}</div>' if p.get("reason") else "")
        + '</div>' for p in prompts)

    chips = [meta.get("unit", "day"), f"{len(prompts)} prompts"]
    if meta.get("growth_zone"):
        chips += [("성장 영역: " if i == 0 else "") + g
                  for i, g in enumerate(meta["growth_zone"])]
        if meta.get("growth_zone_source") == "inferred":
            chips.append("추정")
    chips += [f"{k} {n}" for k, n in
              Counter(p.get("project") for p in prompts if p.get("project")).most_common(3)]

    page = PAGE.substitute(
        css=CSS, js=JS, label=esc(meta.get("label", "")),
        chips="".join(f'<span class="chip">{esc(c)}</span>' for c in chips),
        headline=esc(meta.get("headline", "")),
        main_donut=main, legend=legend,
        amp_mini=mini(AMP), byp_mini=mini(BYP),
        gates=gate_html, offload_n=off, reinvest=reinvest,
        bars=bars or '<span class="empty">기록 없음</span>',
        first=hhmm(prompts[0]["ts"]) if prompts else "",
        last=hhmm(prompts[-1]["ts"]) if prompts else "",
        debts=debts_html, rewrites=rw_html,
        tomorrow=esc((data.get("tomorrow") or {}).get("headline", "—")),
        detail=esc((data.get("tomorrow") or {}).get("detail", "")),
        count=len(prompts),
        filters="".join(
            f'<button data-f="{f}" aria-pressed="{"true" if f=="all" else "false"}">{n}</button>'
            for f, n in (("all", "전체"), ("amplify", "Amplify"), ("offload", "Offload"),
                         ("bypass", "Bypass"), ("neutral", "Neutral"))),
        rows=rows,
        generated=esc(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")))

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"report -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="print the user's prompts as JSON")
    c.add_argument("--root", default="~/.claude/projects")
    c.add_argument("--date", help="YYYY-MM-DD")
    c.add_argument("--since", help="7d, 12h")
    c.add_argument("--session", help="session id or 'current'")
    c.add_argument("--project", help="substring of the project path")
    c.add_argument("--max-chars", type=int, default=800)
    c.add_argument("--out", default="~/amplify-audit/prompts.json",
                   help="where render will read the prompt text from")
    c.set_defaults(func=collect)

    r = sub.add_parser("render", help="read classifications on stdin, write HTML")
    r.add_argument("--out", default="~/amplify-audit/report.html")
    r.add_argument("--prompts", default="~/amplify-audit/prompts.json",
                   help="the file collect wrote")
    r.set_defaults(func=render)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()