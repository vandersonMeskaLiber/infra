#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKLOG="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
HOOK_SCRIPT="$HOME/.cursor/hooks/worklog-cursor.sh"
HOOKS_JSON="$HOME/.cursor/hooks.json"

launchctl bootout "gui/$(id -u)/com.vanderson.worklog.wifi" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.vanderson.worklog.summary" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.vanderson.worklog.dashboard" 2>/dev/null || true

rm -f "$AGENTS/com.vanderson.worklog.wifi.plist"
rm -f "$AGENTS/com.vanderson.worklog.summary.plist"
rm -f "$AGENTS/com.vanderson.worklog.dashboard.plist"
rm -f "$HOOK_SCRIPT"

if [[ -f "$HOOKS_JSON" ]]; then
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / ".cursor" / "hooks.json"
data = json.loads(p.read_text(encoding="utf-8"))
hooks = data.get("hooks", {})
for event, items in list(hooks.items()):
    hooks[event] = [
        h for h in items
        if not (isinstance(h, dict) and "worklog-cursor" in str(h.get("command", "")))
    ]
    if not hooks[event]:
        del hooks[event]
data["hooks"] = hooks
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("[ok] hooks worklog removidos")
PY
fi

echo "Worklog desinstalado (arquivos em $WORKLOG foram mantidos)."
