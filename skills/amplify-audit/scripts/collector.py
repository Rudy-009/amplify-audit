"""Prompt collection from Claude Code and Codex CLI transcripts."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- filters

NOISE_PREFIXES = (
    "<local-command-stdout>", "<system-reminder>",
    "Caveat: The messages below were generated", "[Request interrupted",
    "API Error", "This session is being continued from a previous",
)
NOISE_EXACT = {"continue", "계속", "ㄱ", "y", "yes", "ok", "네", "응", "no", "n"}
BUILTIN_CMDS = {
    "clear", "compact", "config", "context", "cost", "doctor", "exit",
    "export", "help", "hooks", "ide", "init", "login", "logout", "mcp",
    "memory", "model", "permissions", "resume", "rewind", "status",
    "statusline", "terminal-setup", "todos", "upgrade", "usage", "vim",
    "agents", "output-style", "privacy-settings",
}
CMD_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.S)
CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)

# ---------------------------------------------------------------- helpers


def local_ts(raw: str):
    """Parse ISO timestamp to local-tz datetime."""
    try:
        dt = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone()


def text_of(content):
    """Return (text, is_tool_result) from Claude message content."""
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


# ---------------------------------------------------------------- main entry


def collect(args) -> None:
    """Collect user prompts from Claude Code and Codex transcripts."""
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
    out, skipped = [], Counter()

    # --- Claude Code transcripts ---
    claude_root = Path(args.root).expanduser()
    if claude_root.exists():
        if session == "current":
            files = sorted(claude_root.rglob("*.jsonl"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            session = files[0].stem if files else None
        out.extend(_collect_claude(claude_root, start, end, session, args, skipped))

    # --- Codex transcripts ---
    codex_root = Path(args.codex_root).expanduser()
    if codex_root.exists():
        out.extend(_collect_codex(codex_root, start, end, session, args, skipped))

    if not claude_root.exists() and not codex_root.exists():
        sys.exit(f"transcripts not found: tried {claude_root} and {codex_root}")

    out.sort(key=lambda p: p["ts"])
    deduped = []
    for p in out:
        if deduped and deduped[-1]["text"] == p["text"]:
            continue
        deduped.append(p)
    for i, p in enumerate(deduped, 1):
        p["id"] = f"p{i:03d}"

    payload = {"count": len(deduped), "skipped": dict(skipped), "prompts": deduped}
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(blob, encoding="utf-8")

    print(blob)
    print(f"{len(deduped)} prompts -> {out_path}", file=sys.stderr)
    if not deduped:
        print("no prompts matched — try a wider --since or check --root/--codex-root",
              file=sys.stderr)


# ---------------------------------------------------------------- Claude Code parser


def _collect_claude(root, start, end, session, args, skipped):
    """Parse Claude Code transcripts from ~/.claude/projects/."""
    out = []
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
    return out


# ---------------------------------------------------------------- Codex CLI parser


def _collect_codex(root, start, end, session, args, skipped):
    """Parse Codex CLI transcripts from ~/.codex/sessions/.

    Codex JSONL format:
      - type: "session_meta"  → payload.cwd (project)
      - type: "response_item" → payload.type=="message", payload.role=="user"
        payload.content: [{"type": "input_text", "text": "..."}]
      - timestamp at top level
    """
    out = []
    for f in sorted(root.rglob("*.jsonl")):
        if session and session not in f.stem:
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        project = ""
        for line in lines:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = r.get("type", "")
            payload = r.get("payload") or {}

            # Extract project from session_meta
            if rtype == "session_meta":
                cwd = payload.get("cwd", "")
                project = Path(cwd).name if cwd else ""
                continue

            # Only user messages
            if rtype != "response_item":
                skipped["not_user"] += 1
                continue
            if payload.get("type") != "message" or payload.get("role") != "user":
                skipped["not_user"] += 1
                continue

            # Extract text from content
            content = payload.get("content", [])
            if isinstance(content, str):
                txt = content
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "input_text":
                        parts.append(block.get("text", ""))
                txt = "\n".join(p for p in parts if p)
            else:
                continue

            if args.project and args.project.lower() not in project.lower():
                continue

            ts = local_ts(r.get("timestamp", ""))
            if start and ts and not (start <= ts < end):
                skipped["out_of_range"] += 1
                continue

            txt = txt.strip()
            if (not txt or txt.startswith(NOISE_PREFIXES)
                    or txt.lower() in NOISE_EXACT or len(txt) < 2):
                skipped["noise"] += 1
                continue

            cut = len(txt) > args.max_chars
            out.append({"ts": ts.isoformat() if ts else "",
                        "project": project or f.parent.name,
                        "text": txt[:args.max_chars] + (" …[truncated]" if cut else "")})
    return out
