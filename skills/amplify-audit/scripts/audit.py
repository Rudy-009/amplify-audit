#!/usr/bin/env python3
"""amplify-audit — two subcommands.

  collect : read Claude Code / Codex transcripts, print the user's prompts as JSON
            and save them to --out (default ~/amplify-audit/prompts.json)
  render  : read the saved prompts from --prompts and the classifications
            from stdin, join them by id, write the HTML report

Stdlib only.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collector import collect
from renderer import render


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="print the user's prompts as JSON")
    c.add_argument("--root", default="~/.claude/projects",
                   help="Claude Code transcripts root (default: ~/.claude/projects)")
    c.add_argument("--codex-root", default="~/.codex/sessions",
                   help="Codex CLI transcripts root (default: ~/.codex/sessions)")
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
