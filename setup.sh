#!/usr/bin/env bash
set -e

echo "=== cli-usage — Linux Setup ==="

# 1. Install Python GIR typelib for Ayatana AppIndicator3
echo "[1/4] Installing system dependencies..."
sudo apt-get install -y \
    gir1.2-ayatanaappindicator3-0.1 \
    gnome-shell-extension-appindicator \
    python3-gi \
    python3-gi-cairo

# 2. Enable the AppIndicator GNOME extension
echo "[2/4] Enabling AppIndicator GNOME extension..."
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || \
    echo "  ⚠  Could not auto-enable extension — enable it manually via GNOME Extensions app"

# 3. Install the autostart .desktop entry (starts on login)
echo "[3/4] Installing autostart entry..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
SCRIPT_PATH="$(realpath "$(dirname "$0")/cli_usage_gtk.py")"

# Clean up the old desktop file from when this project was named ai-tray.
rm -f "$AUTOSTART_DIR/ai-cli-tray.desktop"

cat > "$AUTOSTART_DIR/cli-usage.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=cli-usage
Comment=Tray indicator showing rate-limit usage for Claude Code, Codex, Gemini CLI
Exec=python3 $SCRIPT_PATH
Icon=network-transmit-receive
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF

# 4. Launch it now (background)
echo "[4/4] Launching tray indicator..."
pkill -f cli_usage_gtk.py 2>/dev/null || true
pkill -f ai_tray.py       2>/dev/null || true
nohup python3 "$SCRIPT_PATH" >/tmp/cli-usage.log 2>&1 &

echo ""
echo "Done! The tray icon should appear next to the battery/clock."
echo ""
echo "If the icon is missing:"
echo "  1. Install the GNOME extension: https://extensions.gnome.org/extension/615/appindicator-support/"
echo "     or run:  sudo apt install gnome-shell-extension-appindicator"
echo "  2. Log out and back in (Wayland needs a session restart to pick up new extensions)."
echo "  3. Enable the extension via the GNOME Extensions app."
echo ""
echo "Log:  tail -f /tmp/cli-usage.log"
