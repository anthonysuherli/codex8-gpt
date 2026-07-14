#!/usr/bin/env bash
# codex8 installer — wires the MCP server into ~/.codex/config.toml and links skills.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${CODEX_HOME:-$HOME/.codex}/config.toml"
SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"

[ -x "$REPO/.venv/bin/python" ] || { echo "run: uv venv && uv pip install -e . first"; exit 1; }

mkdir -p "$(dirname "$CONFIG")" "$SKILLS_DIR"
touch "$CONFIG"

if grep -q '^\[mcp_servers\.codex8\]' "$CONFIG"; then
  echo "config.toml already has [mcp_servers.codex8] — leaving it untouched"
else
  printf '\n[mcp_servers.codex8]\ncommand = "%s"\nargs = ["-m", "codex8.mcp.server"]\n' \
    "$REPO/.venv/bin/python" >> "$CONFIG"
  echo "registered [mcp_servers.codex8] in $CONFIG"
fi

for s in resume search explore projects; do
  ln -sfn "$REPO/skills/$s" "$SKILLS_DIR/codex8-$s"
done
echo "linked skills: codex8-{resume,search,explore,projects} → $SKILLS_DIR"
echo "done — restart Codex to pick up the server."
