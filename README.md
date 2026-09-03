<p align="center">
  <img src="assets/logo.svg" alt="cli-usage logo" width="720">
</p>

<h1 align="center">cli-usage</h1>

<p align="center">
  Never get surprised by AI CLI rate limits again.
</p>

<p align="center">
  <img alt="Python 3.9+" src="https://img.shields.io/badge/Python-3.9%2B-blue">
  <img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Vibe coded" src="https://img.shields.io/badge/vibe-coded-purple">
</p>

<p align="center">
  <strong>A tiny tray/menu-bar indicator for Claude Code and Codex CLI usage.</strong>
</p>

> **Note:** This project was vibe coded — built quickly with AI-assisted flow, practical first, polished enough to ship.

## Preview

<p align="center">
  <img src="assets/screenshot.svg" alt="cli-usage tray preview" width="820">
</p>

## What it tracks

`cli-usage` keeps your remaining quota visible at a glance and shows:

- **one tray icon per provider** on Linux — `CC 86/32%` (Claude: 5h / weekly) and `CX 77%` (Codex), with the numbers drawn *into* the icon and colour-coded green/amber/red
- a single colour-coded icon with a per-provider hover title on macOS/Windows
- account/auth status, every rate-limit window with its reset time, per-model limits (e.g. Weekly Fable, GPT-5.3-Codex-Spark) and credits in the click menu
- one-click terminal shortcuts for each installed CLI

## Supported CLIs

| CLI | Status | What shows |
| --- | --- | --- |
| **Claude Code** | Supported | Account, tier, 5h limit, weekly limit, per-model weekly limits (from the API's `limits[]`), extra usage |
| **Codex CLI** | Supported | Account, plan, 5h/weekly windows (labelled by real duration), per-model sub-limits, credits |

Both providers **self-refresh an expired access token** from the CLI's stored refresh token, so the tray doesn't show "re-login required" just because a token aged out — only when the refresh token itself is revoked.

> Gemini CLI / Antigravity are intentionally **not** shown: Google exposes no per-window quota through a documented endpoint, and a row without numbers adds nothing.

## Cool bits

- Cross-platform tray frontend for **macOS**, **Windows**, and **Linux** using `pystray`
- Native GTK/AppIndicator frontend for Linux with **one icon per provider**
- Auto-refreshes every 60 seconds; numbers are always shown in the same **5h / weekly** order, so they never "switch" on you
- Color-coded status cues in the app:
  - 🟢 green = healthy
  - 🟡 yellow = under 30% left
  - 🔴 red = under 10% left
- On Linux the numbers are rendered **into the icon** (GNOME does not reliably draw AppIndicator text labels), and each icon re-asserts itself every cycle so GNOME can't quietly drop a provider whose value is static
- On Linux the tray runs as a **supervised systemd user service** with a watchdog: it auto-recovers from crashes, display hiccups, and a frozen main loop; **Quit** from the menu stops it, and a **"CLI Usage Tray"** start-menu launcher brings it back
- Menu rows include colored status icons beside each limit; Linux GTK menus use real colored text via Pango markup
- Unified `install.py` plus small OS wrapper scripts for Linux, macOS, and Windows
- No token logging and no extra analytics
- Pinned dependency files: `requirements.txt` and `pyproject.toml`
- Provider response shape validation before rendering usage
- Retry/backoff around transient network failures and 429/5xx responses
- Unit tests for formatting, validation, retry behavior, and installer helpers

## Install in 30 seconds

Clone the repository:

```bash
git clone https://github.com/nimaansari/CLI-Usage.git
cd CLI-Usage
```

### Recommended: unified installer

The easiest path is the new cross-platform installer:

```bash
python3 install.py
```

It will:

- check Python version
- choose the best frontend for your OS
- create a local `.venv` and install pinned Python dependencies when needed
- create a per-user startup/login entry — on **Linux + GTK** this is a supervised systemd user service (`cli-usage-tray.service`, with a watchdog) plus a start-menu launcher; on other platforms a login item
- launch the tray app (on Linux + GTK the service starts it)

Useful installer flags:

```bash
python3 install.py --frontend xplat      # force pystray frontend
python3 install.py --frontend gtk        # force Linux GTK/AppIndicator frontend
python3 install.py --no-autostart        # install/run without login startup
python3 install.py --no-launch           # install only, do not launch now
python3 install.py --skip-deps           # do not install Python packages
python3 install.py --venv .venv-cli-usage # choose a custom virtualenv path
python3 install.py --dry-run             # preview actions without changing files
```

### Linux

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` now delegates to `install.py --frontend auto --install-system-deps`. The cross-platform frontend uses a local `.venv`, avoiding messy system/user Python installs.
If you do not want `sudo apt-get` system package installation, use:

```bash
python3 install.py --frontend xplat
```

Manual run:

```bash
python3 cli_usage_gtk.py      # Linux GTK frontend
python3 cli_usage_xplat.py    # cross-platform frontend
```

### macOS

```bash
chmod +x setup_macos.sh
./setup_macos.sh
```

Manual run:

```bash
python3 -m pip install --user -r requirements.txt
python3 cli_usage_xplat.py
```

### Windows

From PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

Manual run:

```powershell
python -m pip install --user -r requirements.txt
python .\cli_usage_xplat.py
```

## Requirements

### Common

- Python 3.9+
- The CLI tools you want to monitor installed and authenticated:
  - `claude`
  - `codex`

### macOS / Windows / generic Linux frontend

The installer creates a local virtual environment automatically:

```bash
python3 install.py --frontend xplat
```

Manual install if you prefer managing your own environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python cli_usage_xplat.py
```

### Linux GTK/AppIndicator frontend

Debian/Ubuntu-style systems:

```bash
sudo apt-get install -y \
  gir1.2-ayatanaappindicator3-0.1 \
  gnome-shell-extension-appindicator \
  python3-gi \
  python3-gi-cairo
```

## How it works

`cli_usage_core.py` contains the shared data layer. It detects each CLI (by executable *or* by its auth file, since e.g. an nvm-installed `codex` isn't on a systemd service's PATH), reads local auth/account metadata, and calls the first-party usage endpoints:

- Claude Code: Anthropic OAuth usage endpoint
- Codex CLI: ChatGPT Codex usage endpoint

On a `401` it refreshes the access token from the CLI's stored refresh token (persisting the rotated token back atomically) and retries once. It returns, per provider, the menu rows plus a structured `summary` (`5h` / `weekly` remaining %) that both frontends render from — no re-parsing of formatted text.

Frontends:

- `cli_usage_gtk.py` — Linux GTK/AppIndicator tray frontend
- `cli_usage_xplat.py` — pystray frontend for macOS, Windows, and Linux

## Privacy

This app reads local CLI credential files only to discover the current account and request usage data from the relevant first-party service. It does **not** store tokens, print tokens, or send them anywhere other than the official usage endpoints used by the corresponding CLI provider.

Still, treat this like any local tool that can read CLI auth files: review the code before running it on a machine with sensitive credentials.

## Uninstall

### Linux

GTK frontend (systemd service):

```bash
systemctl --user disable --now cli-usage-tray.service
rm -f ~/.config/systemd/user/cli-usage-tray.service ~/.local/share/applications/cli-usage.desktop
systemctl --user daemon-reload
```

Cross-platform (pystray) frontend:

```bash
rm -f ~/.config/autostart/cli-usage.desktop
pkill -f cli_usage_xplat.py || true
```

### macOS

```bash
launchctl unload ~/Library/LaunchAgents/com.user.cli-usage.plist
rm -f ~/Library/LaunchAgents/com.user.cli-usage.plist
pkill -f cli_usage_xplat.py || true
```

### Windows

```powershell
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\cli-usage.lnk"
```

Then quit the tray app from the menu or stop the Python process.

## Tests

Run the built-in unit tests and installer helper checks:

```bash
python3 -m unittest discover -s tests -v
```

## Troubleshooting

### The tray icons do not appear on Linux

- Make sure AppIndicator support is installed and enabled (`ubuntu-appindicators@ubuntu.com` on Ubuntu, `appindicatorsupport@rgcjonas.gmail.com` upstream).
- On GNOME/Wayland, log out and back in after installing the extension.
- Check the service and its log:

```bash
systemctl --user status cli-usage-tray
journalctl --user -u cli-usage-tray -f
```

- **Both icons vanished after a display glitch / suspend?** GNOME's tray host can go into a zombie state (it owns the `StatusNotifierWatcher` but rejects registrations) while the app is perfectly healthy. Reload the extension:

```bash
gnome-extensions disable ubuntu-appindicators@ubuntu.com && gnome-extensions enable ubuntu-appindicators@ubuntu.com
```

### Why is the number in the icon, not next to it?

GNOME Shell renders an AppIndicator's *icon* reliably but draws its *text label* only intermittently (present after a restart, gone hours later). So on Linux the number is rendered into the icon image itself, e.g. `CC 86/32%`. Its colour is the status: green ≥30% left, amber <30%, red <10%.

### The tray keeps restarting / the log is full of watchdog messages

Check `systemctl --user show cli-usage-tray -p NRestarts`. A climbing counter means the systemd watchdog is killing the app. The heartbeat is sent from the 60 s main-loop timer, so only a genuinely frozen UI should trip it — a slow network call must not. If it misfires, raise `WatchdogSec` in the unit.

### A provider shows `⚠ re-login required`

The tray already tried to refresh the token from the CLI's stored refresh token and that failed — the refresh token itself has been revoked or the account changed. Run the CLI's login (`codex login`, or `/login` inside `claude`); the tray recovers on its next cycle.

### Usage says unavailable

Common causes:

- The CLI is not authenticated.
- The provider changed an internal usage endpoint (the response-shape validator will name the field).
- Network access is blocked.
- The auth file format changed in a new CLI release.

## Roadmap

- [x] README badges and visual polish
- [x] Mock preview image
- [x] Simple logo/hero art
- [x] Colored status icons in menu rows and tray icon
- [x] Pinned dependency file / pyproject metadata
- [x] Unit tests for core behavior
- [x] Provider response schema validation
- [x] Retry/backoff around network calls
- [x] Linux GTK colored text labels
- [x] Cleaner unified installer with dry-run/no-launch/no-autostart modes
- [x] One tray icon per provider with the numbers rendered into the icon (Linux)
- [x] Supervised systemd user service with watchdog auto-recovery (Linux)
- [x] Self-refresh of expired Claude / Codex access tokens
- [x] Manual Quit that stays quit + start-menu launcher (Linux)
- [ ] Native desktop notifications when usage is low
- [ ] Configurable refresh interval
- [ ] Package as a macOS app / Windows executable
- [ ] Optional config file for hiding unused CLIs
- [ ] Real screenshots from each OS

## Project structure

```text
assets/logo.svg        # README hero logo
assets/screenshot.svg  # README preview mockup
install.py             # unified installer; systemd service on Linux+GTK, .venv for xplat
cli_usage_core.py      # shared usage/auth detection, token refresh, structured summary
cli_usage_gtk.py       # Linux AppIndicator UI — one icon per provider, numbers in the icon
cli_usage_xplat.py     # pystray cross-platform UI
packaging/             # systemd user unit + start-menu launcher (Linux)
requirements.txt       # pinned runtime deps
pyproject.toml         # project metadata
tests/                 # unit tests
setup*.sh/ps1          # platform startup installers
```

## License

MIT License. See [LICENSE](LICENSE).
