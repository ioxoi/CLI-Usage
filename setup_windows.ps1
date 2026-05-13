# cli-usage — Windows Setup
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== cli-usage — Windows Setup ==="

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $ScriptDir "cli_usage_xplat.py"

# 1. Python deps
Write-Host "[1/3] Installing Python dependencies (pystray, Pillow)..."
python -m pip install --user --upgrade pystray Pillow

# 2. Startup shortcut (runs at login)
Write-Host "[2/3] Creating Startup shortcut..."
$Startup  = [Environment]::GetFolderPath("Startup")
$LnkPath  = Join-Path $Startup "cli-usage.lnk"
$Pythonw  = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $Pythonw) { $Pythonw = (Get-Command python.exe).Source }

# Clean up the old shortcut from when this project was named ai-tray.
$OldLnk = Join-Path $Startup "AI CLI Tray.lnk"
if (Test-Path $OldLnk) { Remove-Item $OldLnk -Force }

$WshShell      = New-Object -ComObject WScript.Shell
$Shortcut      = $WshShell.CreateShortcut($LnkPath)
$Shortcut.TargetPath       = $Pythonw
$Shortcut.Arguments        = "`"$ScriptPath`""
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.WindowStyle      = 7   # Minimized
$Shortcut.Description      = "cli-usage tray indicator"
$Shortcut.Save()

# 3. Launch now (no console window)
Write-Host "[3/3] Launching tray..."
Get-Process -Name pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*cli_usage_xplat.py*" -or $_.CommandLine -like "*ai_tray_xplat.py*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process -FilePath $Pythonw -ArgumentList "`"$ScriptPath`"" -WindowStyle Hidden

Write-Host ""
Write-Host "Done. The 'CLI' icon should appear in the Windows system tray."
Write-Host "Shortcut: $LnkPath"
Write-Host "Uninstall: Remove-Item `"$LnkPath`""
