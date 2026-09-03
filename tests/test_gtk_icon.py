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

    def test_cache_is_bounded_and_just_rendered_icon_survives(self):
        # Every distinct value writes a PNG; unbounded this reached 2.5k files.
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(g, "ICON_DIR", Path(tmp)), patch.object(g, "ICON_CACHE_MAX", 5):
            import os
            for i in range(9):
                _, n = g.render_status_icon("CC", f"CC {i}%", "healthy")
                # The icon we just rendered must always exist right after the
                # call — pruning may never evict it (even with coarse mtimes).
                self.assertTrue((Path(tmp) / f"{n}.png").exists(), f"just-rendered {n} was pruned")
                # give each file a distinct, increasing mtime for deterministic LRU
                os.utime(Path(tmp) / f"{n}.png", (1_000_000 + i, 1_000_000 + i))
            remaining = sorted(p.name for p in Path(tmp).glob("*.png"))
            self.assertLessEqual(len(remaining), 5)
            self.assertIn("cliusage-healthy-CC_8p.png", remaining)   # newest kept
            self.assertNotIn("cliusage-healthy-CC_0p.png", remaining)  # oldest evicted

    def test_icon_name_is_filesystem_safe(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(g, "ICON_DIR", Path(tmp)):
            _, name = g.render_status_icon("CC", "CC 1/2%", "critical")
            self.assertNotIn("/", name)
            self.assertNotIn("%", name)
            self.assertNotIn(" ", name)


if __name__ == "__main__":
    unittest.main()
