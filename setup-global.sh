#!/usr/bin/env bash
# Run once from the spongebob repo root to make spongebob available in every Bob workspace.
#   bash setup-global.sh

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. MCP server — inject into ~/.bob/mcp.json (creates the file if it doesn't exist)
python3 - "$REPO" <<'PY'
import json, sys, pathlib
repo = sys.argv[1]
f = pathlib.Path.home() / ".bob" / "mcp.json"
f.parent.mkdir(parents=True, exist_ok=True)
data = json.loads(f.read_text()) if f.exists() else {}
data.setdefault("mcpServers", {})["spongebob"] = {
    "command": "uv", "args": ["--directory", repo, "run", "spongebob", "mcp"]
}
f.write_text(json.dumps(data, indent=2) + "\n")
print(f"  ✓ MCP server registered in {f}")
PY

# 2. Custom mode
MODES=~/.bob/settings/custom_modes.yaml
mkdir -p ~/.bob/settings
if ! grep -q 'slug: spongebob' "$MODES" 2>/dev/null; then
  cat "$REPO/.bob/custom_modes.yaml" >> "$MODES"
  echo "  ✓ spongebob mode added to $MODES"
else
  echo "  ✓ spongebob mode already in $MODES"
fi

# 3. Skill
mkdir -p ~/.bob/skills/start
cp "$REPO/.bob/skills/start/SKILL.md" ~/.bob/skills/start/SKILL.md
echo "  ✓ start skill copied to ~/.bob/skills/start/SKILL.md"

echo ""
echo "Done. Open any repo in Bob, switch to 'spongebob' mode, and type: onboard this repo"
