import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install


class InstallerTests(unittest.TestCase):
    def test_script_for_frontend(self):
        self.assertEqual(install.script_for_frontend("gtk").name, "cli_usage_gtk.py")
        self.assertEqual(install.script_for_frontend("xplat").name, "cli_usage_xplat.py")

    def test_linux_autostart_writes_desktop_file_to_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                entry = install.install_linux_autostart(Path("/app/cli_usage_xplat.py"), Path("/venv/bin/python"), dry_run=False)
                self.assertTrue(entry.exists())
                text = entry.read_text()
                self.assertIn("Name=cli-usage", text)
                self.assertIn("cli_usage_xplat.py", text)

    def test_dry_run_does_not_write_linux_autostart(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                entry = install.install_linux_autostart(Path("/app/cli_usage_xplat.py"), Path("/venv/bin/python"), dry_run=True)
                self.assertFalse(entry.exists())

    def test_macos_autostart_writes_plist_to_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                entry = install.install_macos_autostart(Path("/app/cli_usage_xplat.py"), Path("/venv/bin/python"), dry_run=False)
                self.assertTrue(entry.exists())
                text = entry.read_text()
                self.assertIn("com.user.cli-usage", text)
                self.assertIn("cli_usage_xplat.py", text)

    def test_windows_autostart_writes_cmd_to_appdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                entry = install.install_windows_autostart(Path("C:/app/cli_usage_xplat.py"), Path("C:/app/.venv/Scripts/pythonw.exe"), dry_run=False)
                self.assertTrue(entry.exists())
                text = entry.read_text()
                self.assertIn("cli_usage_xplat.py", text)

    def test_linux_systemd_writes_unit_and_launcher_and_removes_legacy_autostart(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                legacy = Path(tmp) / ".config" / "autostart" / "cli-usage.desktop"
                legacy.parent.mkdir(parents=True)
                legacy.write_text("[Desktop Entry]\nX-GNOME-Autostart-enabled=true\n")

                unit = install.install_linux_systemd(Path("/app/cli_usage_gtk.py"), Path("/usr/bin/python3"), dry_run=False)

                self.assertTrue(unit.exists())
                text = unit.read_text()
                self.assertIn("Type=notify", text)
                self.assertIn("WatchdogSec=", text)
                self.assertIn("Restart=on-failure", text)
                self.assertIn("ExecStart=/usr/bin/python3 /app/cli_usage_gtk.py", text)
                launcher = Path(tmp) / ".local" / "share" / "applications" / "cli-usage.desktop"
                self.assertTrue(launcher.exists())
                self.assertIn("systemctl --user start cli-usage-tray.service", launcher.read_text())
                self.assertFalse(legacy.exists(), "legacy autostart must be removed to avoid a double launch")

    def test_linux_systemd_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"HOME": tmp}):
                unit = install.install_linux_systemd(Path("/app/cli_usage_gtk.py"), Path("/usr/bin/python3"), dry_run=True)
                self.assertFalse(unit.exists())

    @patch("install.sys")
    def test_linux_gtk_dispatches_to_systemd_not_autostart(self, fake_sys):
        fake_sys.platform = "linux"
        with patch("install.install_linux_systemd", return_value=Path("/u")) as sd, \
             patch("install.install_linux_autostart") as auto:
            install.install_autostart(Path("/app/cli_usage_gtk.py"), Path("/py"), frontend="gtk", dry_run=True)
            sd.assert_called_once()
            auto.assert_not_called()

    @patch("install.sys")
    def test_linux_xplat_still_uses_autostart_desktop(self, fake_sys):
        fake_sys.platform = "linux"
        with patch("install.install_linux_systemd") as sd, \
             patch("install.install_linux_autostart", return_value=Path("/a")) as auto:
            install.install_autostart(Path("/app/cli_usage_xplat.py"), Path("/py"), frontend="xplat", dry_run=True)
            auto.assert_called_once()
            sd.assert_not_called()

    def test_main_dry_run_no_launch_no_autostart(self):
        rc = install.main(["--dry-run", "--skip-deps", "--no-launch", "--no-autostart", "--frontend", "xplat"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
