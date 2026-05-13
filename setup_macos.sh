#!/usr/bin/env bash
set -e

echo "=== cli-usage — macOS Setup ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/cli_usage_xplat.py"

# 1. Python deps
echo "[1/3] Installing Python dependencies (pystray, Pillow)..."
python3 -m pip install --user --upgrade pystray Pillow

# 2. LaunchAgent for login auto-start
echo "[2/3] Installing LaunchAgent..."
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/com.user.cli-usage.plist"
mkdir -p "$PLIST_DIR"

# Clean up the old LaunchAgent from when this project was named ai-tray.
OLD_PLIST="$PLIST_DIR/com.user.ai-cli-tray.plist"
if [ -f "$OLD_PLIST" ]; then
    launchctl unload "$OLD_PLIST" 2>/dev/null || true
    rm "$OLD_PLIST"
fi

PYTHON_BIN="$(command -v python3)"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>           <string>com.user.cli-usage</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$SCRIPT_PATH</string>
    </array>
    <key>RunAtLoad</key>       <true/>
    <key>KeepAlive</key>       <false/>
    <key>StandardOutPath</key> <string>/tmp/cli-usage.log</string>
    <key>StandardErrorPath</key><string>/tmp/cli-usage.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load   "$PLIST"

# 3. Launch now
echo "[3/3] Launching tray..."
pkill -f cli_usage_xplat.py 2>/dev/null || true
pkill -f ai_tray_xplat.py   2>/dev/null || true
nohup "$PYTHON_BIN" "$SCRIPT_PATH" >/tmp/cli-usage.log 2>&1 &

echo ""
echo "Done. The 'CLI' icon should appear in the macOS menu bar."
echo "Log: tail -f /tmp/cli-usage.log"
echo "Uninstall: launchctl unload $PLIST && rm $PLIST"
