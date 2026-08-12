import unittest

try:
    import cli_usage_gtk as g
    HAVE_GTK = True
except Exception:
    HAVE_GTK = False


@unittest.skipUnless(HAVE_GTK, "GTK (gi) not importable in this environment")
class TrayLabelTests(unittest.TestCase):
    def test_both_windows_fixed_order(self):
        info = {"installed": True, "summary": {"5h": 94, "weekly": 71}}
        self.assertEqual(g.tray_label("CC", info), "🟢 CC 94/71")

    def test_weekly_only_shows_dash_for_missing_5h(self):
        info = {"installed": True, "summary": {"5h": None, "weekly": 85}}
        self.assertEqual(g.tray_label("CX", info), "🟢 CX –/85")

    def test_color_follows_worse_of_two_windows(self):
        # 5h healthy but weekly critical → red prefix.
        info = {"installed": True, "summary": {"5h": 94, "weekly": 8}}
        self.assertEqual(g.tray_label("CC", info), "🔴 CC 94/8")

    def test_not_installed(self):
        info = {"installed": False, "summary": {"5h": None, "weekly": None}}
        self.assertEqual(g.tray_label("CX", info), "⚪ CX —")

    def test_installed_but_no_numbers(self):
        info = {"installed": True, "summary": {"5h": None, "weekly": None}}
        self.assertEqual(g.tray_label("CC", info), "⚪ CC –/–")

    def test_worst_of_ignores_missing(self):
        self.assertEqual(g.worst_of({"summary": {"5h": None, "weekly": 85}}), 85)
        self.assertIsNone(g.worst_of({"summary": {"5h": None, "weekly": None}}))


if __name__ == "__main__":
    unittest.main()
