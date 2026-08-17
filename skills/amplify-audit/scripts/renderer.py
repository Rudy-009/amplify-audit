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

from constants import (
    AMBIGUITY, AMP, BYP, GATES, JUDGEMENT_FIELDS,
    LABELS, TAG_VAR, VERDICT_VAR,
)

# ---------------------------------------------------------------- template

TEMPLATE_PATH = Path(__file__).parent / "template.html"


def _load_template() -> Template:
    return Template(TEMPLATE_PATH.read_text(encoding="utf-8"))


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

    merged, unjudged, bad_amb = [], [], []
    for p in prompts:
        j = by_id.pop(p.get("id"), None)
        if j is None:
            unjudged.append(p.get("id"))
        else:
            p = {**p, **{k: v for k, v in j.items() if k in JUDGEMENT_FIELDS}}
            if j.get("confidence") == "low":
                p["ambiguity"] = j.get("low_reason") or p.get("ambiguity")
                p["verdict"] = "ambiguous"
            amb = p.get("verdict") == "ambiguous"
            if amb and p.get("ambiguity") not in AMBIGUITY:
                bad_amb.append(f"{p.get('id')}(ambiguity 없음)")
                p["ambiguity"] = "context"
            elif p.get("ambiguity") and not amb:
                bad_amb.append(f"{p.get('id')}(ambiguous 아닌데 ambiguity)")
                p.pop("ambiguity", None)
        merged.append(p)

    for label, ids in (("no judgement", unjudged), ("unknown id", list(by_id)),
                       ("ambiguity", bad_amb), ("duplicate id", dupes)):
        if ids:
            shown = ", ".join(str(i) for i in ids[:8])
            more = f" (+{len(ids) - 8})" if len(ids) > 8 else ""
            print(f"warning: {len(ids)} {label}: {shown}{more}", file=sys.stderr)
    return merged


# ---------------------------------------------------------------- render


def render(args) -> None:
    """Read classifications from stdin, join with prompts, write HTML report."""
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

    v = Counter(p.get("verdict", "neutral") for p in prompts)
    amp, off, byp, neu = v["amplify"], v["offload"], v["bypass"], v["neutral"]
    classified = amp + off + byp
    pct = round(amp / classified * 100) if classified else 0

    ring = donut([(amp, VERDICT_VAR["amplify"]), (off, VERDICT_VAR["offload"]),
                  (byp, VERDICT_VAR["bypass"])])
    main = (f'<div class="dw">{ring}'
            f'<div class="mid"><b>{pct}%</b><span>Amplify</span>'
            f'<span class="den">/ {classified}건</span></div></div>')

    legend = "".join(
        f'<div class="lg"><span class="dot" style="background:var({VERDICT_VAR[k]})"></span>'
        f'<span class="nm">{nm}</span><span class="vl">{n}</span></div>'
        for nm, n, k in (("Amplify", amp, "amplify"), ("Offload", off, "offload"),
                         ("Bypass", byp, "bypass")))
    amb_counts = Counter(p.get("ambiguity", "context")
                         for p in prompts if p.get("verdict") == "ambiguous")
    for nm, n, note in (("Neutral", neu, "판단했고 의미 없음"),
                        ("Ambiguous · 맥락 부족", amb_counts["context"], "근거가 프롬프트 밖에"),
                        ("Ambiguous · 프롬프트 자체", amb_counts["prompt"], "덜 여문 질문")):
        if n:
            legend += (f'<div class="lg off"><span class="dot hollow"></span>'
                       f'<span class="nm">{nm}<em>{note}</em></span>'
                       f'<span class="vl">{n}</span></div>')

    counts = Counter(p.get("tag", "none") for p in prompts)

    def mini(tags):
        svg = donut([(counts.get(t, 0), TAG_VAR[t]) for t in tags], size=84, thickness=13)
        keys = "".join(
            f'<div class="k"><i style="background:var({TAG_VAR[t]});'
            f'{"opacity:.35" if not counts.get(t) else ""}"></i>{LABELS[t][0]}'
            f'<b>{counts.get(t, 0)}</b></div>' for t in tags)
        return f'<div class="mini"><div class="dw">{svg}</div><div class="keys">{keys}</div></div>'

    lengths = [len(p.get("text", "")) for p in prompts] or [1]
    top = max(max(lengths), 1)
    bars = "".join(
        f'<button data-id="{esc(p.get("id"))}" '
        f'style="height:{14 + 76 * min(1.0, len(p.get("text", "")) / top):.0f}px;'
        f'background:var({TAG_VAR.get(p.get("tag", "none"), "--gray")})" '
        f'title="{esc(hhmm(p.get("ts", "")))} · {esc(LABELS.get(p.get("tag", "none"), ("", ""))[0])} · '
        f'{esc(p.get("text", "")[:60])}"></button>' for p in prompts)

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

    def lean(p) -> str:
        t = p.get("tag", "none")
        return "ambiguous" if p.get("verdict") == "ambiguous" and t == "none" else t

    def bucket(p) -> str:
        return p.get("verdict", "neutral")

    rows = "".join(
        f'<div class="p {esc(p.get("verdict", "neutral"))}" id="{esc(p.get("id"))}" '
        f'data-v="{esc(bucket(p))}">'
        f'<div class="top"><span>{hhmm(p.get("ts", ""))}</span>'
        f'<span>{esc(p.get("project"))}</span>'
        f'<span class="tag" style="color:var({TAG_VAR.get(lean(p), "--gray")})">'
        f'{esc(LABELS.get(lean(p), ("Neutral", ""))[0])}</span>'
        + gate_pills(p)
        + (f'<span class="pill">Ambiguous · '
           f'{AMBIGUITY.get(p.get("ambiguity"), "맥락 부족")}</span>'
           if p.get("verdict") == "ambiguous" else "")
        + f'</div><div class="text">{esc(p.get("text"))}</div>'
        + (f'<div class="reason">{esc(p.get("reason"))}</div>' if p.get("reason") else "")
        + '</div>' for p in prompts)

    page = _load_template().substitute(
        label=esc(meta.get("label", "")),
        main_donut=main, legend=legend,
        amp_mini=mini(AMP), byp_mini=mini(BYP),
        bars=bars or '<span class="empty">기록 없음</span>',
        first=hhmm(prompts[0]["ts"]) if prompts else "",
        last=hhmm(prompts[-1]["ts"]) if prompts else "",
        count=len(prompts),
        filters="".join(
            f'<button data-f="{f}" aria-pressed="{"true" if f == "all" else "false"}">{n}</button>'
            for f, n in (("all", "전체"), ("amplify", "Amplify"), ("offload", "Offload"),
                         ("bypass", "Bypass"), ("neutral", "Neutral"),
                         ("ambiguous", "Ambiguous"))),
        rows=rows,
        generated=esc(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")))

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"report -> {out}")
