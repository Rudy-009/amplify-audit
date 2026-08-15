#!/bin/bash
set -e

REPO="https://github.com/Rudy-009/amplify-audit.git"
SRC_DIR="skills/amplify-audit"

CLAUDE_SKILL_DIR="$HOME/.claude/skills/amplify-audit"
CODEX_SKILL_DIR="$HOME/.agents/skills/amplify-audit"

echo "📦 Installing amplify-audit skill..."
echo ""

# --- Detect platforms ---
INSTALL_CLAUDE=false
INSTALL_CODEX=false

if command -v claude &>/dev/null; then
  INSTALL_CLAUDE=true
fi

if command -v codex &>/dev/null; then
  INSTALL_CODEX=true
fi

# If neither detected, install both (user can remove later)
if [ "$INSTALL_CLAUDE" = false ] && [ "$INSTALL_CODEX" = false ]; then
  echo "   Neither 'claude' nor 'codex' CLI found."
  echo "   Installing to both paths (remove the one you don't need)."
  INSTALL_CLAUDE=true
  INSTALL_CODEX=true
fi

# --- Clone to temp ---
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT
git clone --depth 1 "$REPO" "$TMP_DIR" 2>/dev/null

# --- Install function ---
install_to() {
  local TARGET_DIR="$1"
  local LABEL="$2"
  mkdir -p "$TARGET_DIR"
  cp "$TMP_DIR/$SRC_DIR/SKILL.md" "$TARGET_DIR/"
  cp "$TMP_DIR/$SRC_DIR/audit.py" "$TARGET_DIR/"
  mkdir -p "$TARGET_DIR/agents"
  cp "$TMP_DIR/$SRC_DIR/agents/openai.yaml" "$TARGET_DIR/agents/"
  echo "   ✅ $LABEL → $TARGET_DIR"
}

# --- Install ---
if [ "$INSTALL_CLAUDE" = true ]; then
  install_to "$CLAUDE_SKILL_DIR" "Claude Code"
fi

if [ "$INSTALL_CODEX" = true ]; then
  install_to "$CODEX_SKILL_DIR" "Codex"
fi

echo ""
echo "Done! Usage: \"오늘 프롬프트 분석해줘\""
