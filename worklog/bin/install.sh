#!/bin/bash
set -euo pipefail

# Fonte (repo ou cópia local) e runtime (fora de Documents — exigência do launchd/macOS)
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="${WORKLOG_HOME:-$HOME/.worklog}"

AGENTS="$HOME/Library/LaunchAgents"
CURSOR_DIR="$HOME/.cursor"
HOOK_SCRIPT="$CURSOR_DIR/hooks/worklog-cursor.sh"

echo "[info] source  = $SOURCE"
echo "[info] runtime = $RUNTIME"

mkdir -p "$RUNTIME/logs/state" "$RUNTIME/diario" "$AGENTS" "$CURSOR_DIR/hooks"

# Publica código no runtime (preserva config/logs/diario)
rsync -a \
  --exclude 'config.json' \
  --exclude 'logs/' \
  --exclude 'diario/' \
  --exclude 'dashboard.html' \
  --exclude '.DS_Store' \
  --exclude '.git/' \
  "$SOURCE/" "$RUNTIME/"

chmod +x "$RUNTIME/bin/"*.py "$RUNTIME/bin/"*.sh 2>/dev/null || true

if [[ ! -f "$RUNTIME/config.json" ]]; then
  if [[ -f "$RUNTIME/config.example.json" ]]; then
    cp "$RUNTIME/config.example.json" "$RUNTIME/config.json"
    echo "[aviso] Criado $RUNTIME/config.json a partir do example — revise senhas/SSID."
  elif [[ -f "$SOURCE/config.json" ]]; then
    cp "$SOURCE/config.json" "$RUNTIME/config.json"
    echo "[aviso] Copiado config.json do source → runtime."
  else
    echo "[erro] Falta config.json no runtime e não há example." >&2
    exit 1
  fi
fi

python3 - <<PY
import json
from pathlib import Path
p = Path("$RUNTIME") / "config.json"
cfg = json.loads(p.read_text(encoding="utf-8"))
cfg["worklog_dir"] = "$RUNTIME"
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[ok] worklog_dir = $RUNTIME")
PY

# launchd aponta sempre para o runtime (~/.worklog)
for name in wifi summary dashboard; do
  src="$RUNTIME/launchd/com.vanderson.worklog.${name}.plist"
  dst="$AGENTS/com.vanderson.worklog.${name}.plist"
  sed "s|__WORKLOG_DIR__|$RUNTIME|g" "$src" > "$dst"
done

launchctl bootout "gui/$(id -u)/com.vanderson.worklog.wifi" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.vanderson.worklog.summary" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.vanderson.worklog.dashboard" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENTS/com.vanderson.worklog.wifi.plist"
launchctl bootstrap "gui/$(id -u)" "$AGENTS/com.vanderson.worklog.summary.plist"
launchctl bootstrap "gui/$(id -u)" "$AGENTS/com.vanderson.worklog.dashboard.plist"
launchctl enable "gui/$(id -u)/com.vanderson.worklog.wifi" 2>/dev/null || true
launchctl enable "gui/$(id -u)/com.vanderson.worklog.summary" 2>/dev/null || true
launchctl enable "gui/$(id -u)/com.vanderson.worklog.dashboard" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/com.vanderson.worklog.wifi" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/com.vanderson.worklog.dashboard" 2>/dev/null || true

cat > "$HOOK_SCRIPT" <<EOF
#!/bin/bash
set -u
/usr/bin/python3 "$RUNTIME/bin/cursor_log.py" || echo '{}'
exit 0
EOF
chmod +x "$HOOK_SCRIPT"

python3 - <<'PY'
import json
from pathlib import Path

hooks_path = Path.home() / ".cursor" / "hooks.json"
cmd = "./hooks/worklog-cursor.sh"
entries = [{"command": cmd}]

data = {"version": 1, "hooks": {}}
if hooks_path.exists():
    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 1, "hooks": {}}

data.setdefault("version", 1)
data.setdefault("hooks", {})

for event in ("beforeSubmitPrompt", "sessionStart", "sessionEnd", "stop"):
    existing = data["hooks"].get(event, [])
    filtered = [
        h for h in existing
        if not (isinstance(h, dict) and "worklog-cursor" in str(h.get("command", "")))
    ]
    filtered.extend(entries)
    data["hooks"][event] = filtered

hooks_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[ok] hooks em {hooks_path}")
PY

# atalho conveniente
ln -sfn "$RUNTIME" "$HOME/Documents/worklog" 2>/dev/null || true

/usr/bin/python3 "$RUNTIME/bin/wifi_watch.py" --once || true

echo ""
echo "Worklog instalado."
echo "  Repo/source: $SOURCE"
echo "  Runtime:     $RUNTIME   (launchd + logs + config.json)"
echo "  Painel:      http://127.0.0.1:8765/"
echo ""
echo "Fluxo: edite em infra/worklog → rode bash bin/install.sh para publicar no runtime."
echo "Reinicie o Cursor para ativar os hooks."
