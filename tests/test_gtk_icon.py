import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import cli_usage_gtk as g
    HAVE_GTK = True
except Exception:
    HAVE_GTK = False


@unittest.skipUnless(HAVE_GTK, "GTK (gi) not importable in this environment")
class UsageStateTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(g.usage_state(None), "unknown")
        self.assertEqual(g.usage_state(5), "critical")
        self.assertEqual(g.usage_state(29), "warning")
        self.assertEqual(g.usage_state(30), "healthy")
        self.assertEqual(g.usage_state(100), "healthy")


@unittest.skipUnless(HAVE_GTK, "GTK (gi) not importable in this environment")
class RenderStatusIconTests(unittest.TestCase):
    """The number is drawn INTO the icon (GNOME ignores text labels), so the
    renderer is the thing that must be right. Runs headless via cairo."""

    def _png_size(self, path):
        d = path.read_bytes()
        self.assertEqual(d[:8], b"\x89PNG\r\n\x1a\n")
        return struct.unpack(">II", d[16:24])

    def test_renders_valid_png_named_by_content(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(g, "ICON_DIR", Path(tmp)):
            theme_dir, name = g.render_status_icon("CC", "CC 86/32%", "healthy")
            self.assertEqual(theme_dir, tmp)
            self.assertEqual(name, "cliusage-healthy-CC_86-32p")   # '/'→'-', '%'→'p'
            w, h = self._png_size(Path(tmp) / f"{name}.png")
            self.assertEqual(h, 44)
            self.assertGreater(w, 44)                                 # wide badge

    def test_variant_suffix_changes_name_so_gnome_reloads(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(g, "ICON_DIR", Path(tmp)):
            _, a = g.render_status_icon("CX", "CX 77%", "healthy", "-a")
            _, b = g.render_status_icon("CX", "CX 77%", "healthy", "-b")
            self.assertNotEqual(a, b)
            self.assertTrue((Path(tmp) / f"{a}.png").exists())
            self.assertTrue((Path(tmp) / f"{b}.png").exists())

    def test_icon_name_is_filesystem_safe(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(g, "ICON_DIR", Path(tmp)):
            _, name = g.render_status_icon("CC", "CC 1/2%", "critical")
            self.assertNotIn("/", name)
            self.assertNotIn("%", name)
            self.assertNotIn(" ", name)


if __name__ == "__main__":
    unittest.main()
