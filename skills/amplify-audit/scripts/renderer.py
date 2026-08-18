"""HTML report renderer for amplify-audit."""

from __future__ import annotations

import html
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from string import Template

from constants import LABELS, AMP, BYP, GATES, TAG_VAR, JUDGEMENT_FIELDS

# ---------------------------------------------------------------- template

_TEMPLATE = Template((Path(__file__).parent / "template.html").read_text(encoding="utf-8"))

# ---------------------------------------------------------------- helpers


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


# ---------------------------------------------------------------- join


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


# ---------------------------------------------------------------- render


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

    page = _TEMPLATE.substitute(
        label=esc(meta.get("label", "")),
        chips="".join(f'<span class="chip">{esc(c)}</span>' for c in chips),
        headline=esc(meta.get("headline", "")),
        main_donut=main, legend=legend,
        amp_mini=mini(AMP), byp_mini=mini(BYP),
        gates=gate_html, offload_n=off, reinvest=reinvest,
        bars=bars or '<span class="empty">기록 없음</span>',
        first=hhmm(prompts[0]["ts"]) if prompts else "",
        last=hhmm(prompts[-1]["ts"]) if prompts else "",
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
