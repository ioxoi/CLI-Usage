import io
import json
import urllib.error
import unittest
from unittest.mock import Mock, patch

import cli_usage_core as core


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class CoreFormattingTests(unittest.TestCase):
    def test_bar_and_status_icons(self):
        self.assertEqual(core._bar(100), "[████████████] 100% left")
        self.assertEqual(core._bar(0), "[░░░░░░░░░░░░] 0% left")
        self.assertEqual(core._bar(None), "")
        self.assertEqual(core._status_icon(80), "🟢")
        self.assertEqual(core._status_icon(20), "🟡")
        self.assertEqual(core._status_icon(5), "🔴")
        self.assertEqual(core._status_icon(None), "⚪")

    def test_limit_row_contains_colored_icon(self):
        self.assertIn("🟡", core._limit_row("5h limit", 75, None, "5h"))
        self.assertIn("25% left", core._limit_row("5h limit", 75, None, "5h"))

    def test_worst_remaining_pct_uses_structured_summary(self):
        data = {
            "Claude Code": {"installed": True, "summary": {"5h": 80, "weekly": 60}},
            "Codex CLI":   {"installed": True, "summary": {"5h": None, "weekly": 8}},
        }
        self.assertEqual(core.worst_remaining_pct(data), 8)
        self.assertIsNone(core.worst_remaining_pct({"Claude Code": {"summary": {}}}))

    def test_summary_badge_formats(self):
        both = {"installed": True, "summary": {"5h": 86, "weekly": 32}}
        one  = {"installed": True, "summary": {"5h": None, "weekly": 77}}
        none = {"installed": True, "summary": {"5h": None, "weekly": None}}
        off  = {"installed": False, "summary": {}}
        self.assertEqual(core.summary_badge("CC", both), "CC 86/32%")
        self.assertEqual(core.summary_badge("CX", one),  "CX 77%")
        self.assertEqual(core.summary_badge("CC", none), "CC")
        self.assertEqual(core.summary_badge("CX", off),  "CX")

    def test_usage_state_thresholds_single_source(self):
        # Shared by both frontends and the menu-row emoji.
        self.assertEqual(core.usage_state(None), "unknown")
        self.assertEqual(core.usage_state(9.9), "critical")
        self.assertEqual(core.usage_state(10), "warning")
        self.assertEqual(core.usage_state(29.9), "warning")
        self.assertEqual(core.usage_state(30), "healthy")
        self.assertEqual(core._status_icon(5), "🔴")
        self.assertEqual(core._status_icon(None), "⚪")

    def test_provider_registry_is_consistent(self):
        self.assertEqual(list(core.PROVIDERS), ["Claude Code", "Codex CLI"])
        self.assertEqual(core.PROVIDER_TAGS, {"Claude Code": "CC", "Codex CLI": "CX"})
        self.assertEqual(core.PROVIDER_CMDS, {"Claude Code": "claude", "Codex CLI": "codex"})
        self.assertEqual(set(core._FETCHERS), set(core.PROVIDERS))  # every provider has a fetcher

    def test_summary_worst(self):
        self.assertEqual(core.summary_worst({"summary": {"5h": 94, "weekly": 8}}), 8)
        self.assertEqual(core.summary_worst({"summary": {"5h": None, "weekly": 85}}), 85)
        self.assertIsNone(core.summary_worst({"summary": {"5h": None, "weekly": None}}))


class ValidationTests(unittest.TestCase):
    def test_validate_claude_usage_accepts_expected_shape(self):
        payload = {"five_hour": {"utilization": 20}, "extra_usage": {"utilization": 0}}
        self.assertIs(core.validate_claude_usage(payload), payload)

    def test_validate_claude_usage_rejects_bad_shape(self):
        with self.assertRaises(core.ProviderResponseError):
            core.validate_claude_usage({"five_hour": {"utilization": "nope"}})

    def test_validate_codex_usage_accepts_expected_shape(self):
        payload = {
            "rate_limit": {"primary_window": {"used_percent": 10}},
            "additional_rate_limits": [
                {"rate_limit": {"secondary_window": {"used_percent": 30}}}
            ],
            "credits": {"has_credits": True},
        }
        self.assertIs(core.validate_codex_usage(payload), payload)

    def test_validate_codex_usage_rejects_bad_shape(self):
        with self.assertRaises(core.ProviderResponseError):
            core.validate_codex_usage({"additional_rate_limits": "wrong"})

    def test_validate_claude_usage_accepts_limits_array(self):
        payload = {
            "five_hour": {"utilization": 5},
            "limits": [
                {"kind": "weekly_scoped", "group": "weekly", "percent": 23,
                 "scope": {"model": {"display_name": "Fable"}}},
            ],
        }
        self.assertIs(core.validate_claude_usage(payload), payload)

    def test_validate_claude_usage_rejects_bad_limit_percent(self):
        with self.assertRaises(core.ProviderResponseError):
            core.validate_claude_usage({"limits": [{"percent": "nope"}]})


class ClaudeModelBarometerTests(unittest.TestCase):
    def _rows(self, payload):
        creds = json.dumps({"claudeAiOauth": {"accessToken": "tok"}})
        with patch("cli_usage_core.shutil.which", return_value="/usr/bin/claude"), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text", return_value=creds), \
             patch("cli_usage_core._http_json", return_value=payload):
            return [r[0] for r in core.claude_data()["rows"]]

    def test_weekly_scoped_model_renders_named_row(self):
        rows = self._rows({
            "five_hour": {"utilization": 6, "resets_at": None},
            "seven_day": {"utilization": 29, "resets_at": None},
            "limits": [
                {"group": "weekly", "percent": 23, "resets_at": None,
                 "scope": {"model": {"display_name": "Fable"}}},
            ],
        })
        self.assertTrue(any("Weekly Fable" in r and "77% left" in r for r in rows))

    def test_summary_reports_5h_and_weekly_remaining(self):
        creds = json.dumps({"claudeAiOauth": {"accessToken": "tok"}})
        payload = {
            "five_hour": {"utilization": 6, "resets_at": None},
            "seven_day": {"utilization": 29, "resets_at": None},
        }
        with patch("cli_usage_core.shutil.which", return_value="/usr/bin/claude"), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text", return_value=creds), \
             patch("cli_usage_core._http_json", return_value=payload):
            summary = core.claude_data()["summary"]
        self.assertEqual(summary, {"5h": 94, "weekly": 71})

    def test_unscoped_limits_do_not_duplicate_rows(self):
        rows = self._rows({
            "seven_day": {"utilization": 29, "resets_at": None},
            "limits": [
                {"kind": "weekly_all", "group": "weekly", "percent": 29},
                {"group": "session", "percent": 5},
            ],
        })
        # Only the top-level Weekly row; unscoped limits[] entries are skipped.
        self.assertEqual(sum("Weekly" in r for r in rows), 1)


class CodexDetectionTests(unittest.TestCase):
    def test_installed_via_auth_file_when_not_on_path(self):
        # Simulates a systemd user service whose PATH lacks the nvm bin dir:
        # `codex` is not resolvable but ~/.codex/auth.json exists.
        payload = {"email": "x@y.z", "plan_type": "plus", "rate_limit": {}}
        with patch("cli_usage_core.shutil.which", return_value=None), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text",
                   return_value=json.dumps({"tokens": {"access_token": "t"}})), \
             patch("cli_usage_core._http_json", return_value=payload):
            result = core.codex_data()
        self.assertTrue(result["installed"])
        self.assertFalse(any("not installed" in r[0] for r in result["rows"]))

    def test_not_installed_when_no_binary_and_no_auth(self):
        with patch("cli_usage_core.shutil.which", return_value=None), \
             patch("cli_usage_core.Path.exists", return_value=False):
            result = core.codex_data()
        self.assertFalse(result["installed"])
        self.assertEqual(result["summary"], {"5h": None, "weekly": None})

    def test_summary_maps_weekly_only_plan(self):
        # Plus plan: primary_window is the weekly window, no 5h.
        payload = {"email": "x@y.z", "plan_type": "plus", "rate_limit": {
            "primary_window": {"used_percent": 15, "limit_window_seconds": 604800},
        }}
        with patch("cli_usage_core.shutil.which", return_value=None), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text",
                   return_value=json.dumps({"tokens": {"access_token": "t"}})), \
             patch("cli_usage_core._http_json", return_value=payload):
            summary = core.codex_data()["summary"]
        self.assertEqual(summary, {"5h": None, "weekly": 85})


class CodexWindowLabelTests(unittest.TestCase):
    def test_weekly_window_by_duration(self):
        label, kind = core._codex_window_label({"limit_window_seconds": 604800})
        self.assertEqual((label, kind), ("Weekly limit", "week"))

    def test_five_hour_window_by_duration(self):
        label, kind = core._codex_window_label({"limit_window_seconds": 18000})
        self.assertEqual((label, kind), ("5h limit", "5h"))

    def test_missing_duration_uses_fallback(self):
        self.assertEqual(core._codex_window_label({}, "Weekly limit", "week"),
                         ("Weekly limit", "week"))


class ErrorRowTests(unittest.TestCase):
    def test_http_401_maps_to_relogin_row(self):
        error = urllib.error.HTTPError("url", 401, "unauthorized", {}, io.BytesIO())
        rows = core._usage_error_rows(error, "codex login")
        self.assertIn("re-login required", rows[0][0])
        self.assertIn("codex login", rows[0][0])

    def test_other_http_error_shows_status_code(self):
        error = urllib.error.HTTPError("url", 503, "down", {}, io.BytesIO())
        rows = core._usage_error_rows(error, "codex login")
        self.assertIn("HTTP 503", rows[0][0])

    def test_non_http_error_shows_type_name(self):
        rows = core._usage_error_rows(TimeoutError(), "codex login")
        self.assertIn("TimeoutError", rows[0][0])


class HttpTests(unittest.TestCase):
    @patch("cli_usage_core.time.sleep", return_value=None)
    @patch("cli_usage_core.urllib.request.urlopen")
    def test_http_json_retries_429_then_succeeds(self, urlopen, _sleep):
        headers = {"Retry-After": "0"}
        error = urllib.error.HTTPError("url", 429, "rate limited", headers, io.BytesIO())
        urlopen.side_effect = [error, FakeResponse({"ok": True})]
        self.assertEqual(core._http_json("https://example.test", {}, retries=2), {"ok": True})
        self.assertEqual(urlopen.call_count, 2)

    @patch("cli_usage_core.time.sleep", return_value=None)
    @patch("cli_usage_core.urllib.request.urlopen")
    def test_http_json_does_not_retry_400(self, urlopen, _sleep):
        error = urllib.error.HTTPError("url", 400, "bad", {}, io.BytesIO())
        urlopen.side_effect = error
        with self.assertRaises(urllib.error.HTTPError):
            core._http_json("https://example.test", {}, retries=3)
        self.assertEqual(urlopen.call_count, 1)


class CodexRefreshTests(unittest.TestCase):
    def test_401_refreshes_token_and_retries(self):
        auth = json.dumps({"tokens": {"access_token": "old", "refresh_token": "rt"}})
        payload = {"email": "x@y.z", "plan_type": "pro", "rate_limit": {
            "primary_window": {"used_percent": 10, "limit_window_seconds": 604800}}}
        usage_calls = {"n": 0}

        def fake_http(url, headers, **kw):
            if url == core.CODEX_TOKEN_URL:
                return {"access_token": "new", "refresh_token": "rt2", "id_token": "id2"}
            if url == core.CODEX_USAGE_URL:
                usage_calls["n"] += 1
                if usage_calls["n"] == 1:
                    raise urllib.error.HTTPError(url, 401, "expired", {}, io.BytesIO())
                self.assertEqual(headers["Authorization"], "Bearer new")  # retried with fresh token
                return payload
            raise AssertionError(f"unexpected url {url}")

        with patch("cli_usage_core.shutil.which", return_value="/usr/bin/codex"), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text", return_value=auth), \
             patch("cli_usage_core._atomic_write_json") as write, \
             patch("cli_usage_core._http_json", side_effect=fake_http):
            result = core.codex_data()

        self.assertEqual(usage_calls["n"], 2)          # refreshed + retried
        self.assertEqual(result["summary"]["weekly"], 90.0)
        self.assertFalse(any("re-login" in r[0] for r in result["rows"]))
        write.assert_called_once()                      # rotated tokens persisted

    def test_401_without_refresh_token_shows_relogin(self):
        auth = json.dumps({"tokens": {"access_token": "old"}})  # no refresh_token

        def fake_http(url, headers, **kw):
            if url == core.CODEX_USAGE_URL:
                raise urllib.error.HTTPError(url, 401, "expired", {}, io.BytesIO())
            raise AssertionError(f"unexpected url {url}")

        with patch("cli_usage_core.shutil.which", return_value="/usr/bin/codex"), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text", return_value=auth), \
             patch("cli_usage_core._http_json", side_effect=fake_http):
            result = core.codex_data()

        self.assertTrue(any("re-login required" in r[0] for r in result["rows"]))

    def test_refresh_persists_rotated_refresh_token(self):
        auth = json.dumps({"tokens": {"access_token": "old", "refresh_token": "rt"},
                           "auth_mode": "chatgpt"})
        saved = {}

        def fake_http(url, headers, **kw):
            self.assertEqual(url, core.CODEX_TOKEN_URL)
            return {"access_token": "new", "refresh_token": "rotated", "id_token": "id2"}

        with patch("cli_usage_core.Path.read_text", return_value=auth), \
             patch("cli_usage_core._http_json", side_effect=fake_http), \
             patch("cli_usage_core._atomic_write_json", side_effect=lambda p, o: saved.update(o)):
            tok = core.refresh_codex_token(core.Path("/x/auth.json"))

        self.assertEqual(tok, "new")
        self.assertEqual(saved["tokens"]["refresh_token"], "rotated")  # new RT persisted
        self.assertEqual(saved["tokens"]["access_token"], "new")
        self.assertEqual(saved["auth_mode"], "chatgpt")               # other fields preserved


class ClaudeRefreshTests(unittest.TestCase):
    CREDS = json.dumps({"claudeAiOauth": {"accessToken": "old", "refreshToken": "rt",
                                          "subscriptionType": "team"}})

    def _run(self, fake_http):
        with patch("cli_usage_core.shutil.which", return_value="/usr/bin/claude"), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text", return_value=self.CREDS), \
             patch("cli_usage_core._atomic_write_json") as write, \
             patch("cli_usage_core._http_json", side_effect=fake_http):
            return core.claude_data(), write

    def test_401_refreshes_and_retries(self):
        usage = {"n": 0}

        def fake_http(url, headers, **kw):
            if url == core.CLAUDE_TOKEN_URL:
                return {"access_token": "new", "refresh_token": "rt2", "expires_in": 3600}
            if url == core.CLAUDE_USAGE_URL:
                usage["n"] += 1
                if usage["n"] == 1:
                    raise urllib.error.HTTPError(url, 401, "expired", {}, io.BytesIO())
                self.assertEqual(headers["Authorization"], "Bearer new")
                return {"five_hour": {"utilization": 20}, "seven_day": {"utilization": 30}}
            raise AssertionError(url)

        result, write = self._run(fake_http)
        self.assertEqual(usage["n"], 2)
        self.assertEqual(result["summary"], {"5h": 80, "weekly": 70})
        write.assert_called_once()
        saved = write.call_args[0][1]["claudeAiOauth"]
        self.assertEqual(saved["refreshToken"], "rt2")   # rotated RT persisted
        self.assertIn("expiresAt", saved)

    def test_refresh_sends_real_claude_code_version_user_agent(self):
        # Anthropic's token endpoint routes on User-Agent: only a real current
        # "claude-code/<version>" reaches the refresh handler; a made-up name or
        # an old version gets 404 not_found, and a bare urllib UA gets a
        # Cloudflare "403 error code: 1010". So we report the installed version.
        seen = {}

        def fake_http(url, headers, **kw):
            seen.update(headers)
            return {"access_token": "new"}

        core._claude_ua_cache = None
        with patch("cli_usage_core.Path.read_text", return_value=self.CREDS), \
             patch("cli_usage_core._atomic_write_json"), \
             patch("cli_usage_core._http_json", side_effect=fake_http), \
             patch("subprocess.run") as run:
            run.return_value.stdout = "9.8.7 (Claude Code)\n"
            self.assertEqual(core.refresh_claude_token(core.Path("/x")), "new")
        self.assertEqual(seen["User-Agent"], "claude-code/9.8.7")
        self.assertEqual(seen["Accept"], "application/json")
        core._claude_ua_cache = None

    def test_user_agent_falls_back_when_claude_binary_unavailable(self):
        core._claude_ua_cache = None
        with patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(core.claude_user_agent(), f"claude-code/{core.CLAUDE_FALLBACK_VERSION}")
        core._claude_ua_cache = None

    def test_401_when_refresh_fails_shows_relogin(self):
        def fake_http(url, headers, **kw):
            if url == core.CLAUDE_TOKEN_URL:
                raise urllib.error.HTTPError(url, 400, "bad", {}, io.BytesIO())
            raise urllib.error.HTTPError(url, 401, "expired", {}, io.BytesIO())

        result, _ = self._run(fake_http)
        self.assertTrue(any("re-login required" in r[0] for r in result["rows"]))


class ConcurrentCredentialWriteTests(unittest.TestCase):
    """The owning CLI may rewrite its credential file while we refresh. Our
    write must merge into the CURRENT file, never clobber it with a stale copy."""

    def test_codex_refresh_preserves_fields_written_by_cli_meanwhile(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            auth = core.Path(tmp) / "auth.json"
            auth.write_text(json.dumps({"tokens": {"access_token": "old", "refresh_token": "rt"},
                                        "auth_mode": "chatgpt"}))

            def fake_http(url, headers, **kw):
                # Simulate the Codex CLI rewriting the file *during* our refresh,
                # adding a key we know nothing about.
                cur = json.loads(auth.read_text())
                cur["cli_added_meanwhile"] = True
                auth.write_text(json.dumps(cur))
                return {"access_token": "new", "refresh_token": "rt2"}

            with patch("cli_usage_core._http_json", side_effect=fake_http):
                self.assertEqual(core.refresh_codex_token(auth), "new")

            final = json.loads(auth.read_text())
            self.assertTrue(final.get("cli_added_meanwhile"), "concurrent CLI write was clobbered")
            self.assertEqual(final["tokens"]["access_token"], "new")
            self.assertEqual(final["tokens"]["refresh_token"], "rt2")
            self.assertEqual(final["auth_mode"], "chatgpt")

    def test_claude_refresh_preserves_fields_written_by_cli_meanwhile(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            creds = core.Path(tmp) / ".credentials.json"
            creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "old", "refreshToken": "rt",
                                                           "subscriptionType": "team"}}))

            def fake_http(url, headers, **kw):
                cur = json.loads(creds.read_text())
                cur["claudeAiOauth"]["rateLimitTier"] = "written_by_cli"
                creds.write_text(json.dumps(cur))
                return {"access_token": "new", "refresh_token": "rt2", "expires_in": 60}

            with patch("cli_usage_core._http_json", side_effect=fake_http):
                self.assertEqual(core.refresh_claude_token(creds), "new")

            o = json.loads(creds.read_text())["claudeAiOauth"]
            self.assertEqual(o["rateLimitTier"], "written_by_cli", "concurrent CLI write was clobbered")
            self.assertEqual(o["accessToken"], "new")
            self.assertEqual(o["refreshToken"], "rt2")
            self.assertEqual(o["subscriptionType"], "team")


class PersistFailureTests(unittest.TestCase):
    """If the rotated token can't be saved, the on-disk copy is now dead. We must
    still return the working token for this cycle AND report it loudly."""

    def test_codex_persist_failure_is_reported_not_silent(self):
        auth = json.dumps({"tokens": {"access_token": "old", "refresh_token": "rt"}})
        with patch("cli_usage_core.Path.read_text", return_value=auth), \
             patch("cli_usage_core._http_json", return_value={"access_token": "new", "refresh_token": "rt2"}), \
             patch("cli_usage_core._atomic_write_json", side_effect=OSError("disk full")), \
             patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(core.refresh_codex_token(core.Path("/x/auth.json")), "new")
        self.assertIn("could not write", err.getvalue())
        self.assertIn("disk full", err.getvalue())

    def test_claude_persist_failure_is_reported_not_silent(self):
        creds = json.dumps({"claudeAiOauth": {"accessToken": "old", "refreshToken": "rt"}})
        core._claude_ua_cache = "claude-code/9.9.9"
        with patch("cli_usage_core.Path.read_text", return_value=creds), \
             patch("cli_usage_core._http_json", return_value={"access_token": "new"}), \
             patch("cli_usage_core._atomic_write_json", side_effect=PermissionError("read-only")), \
             patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(core.refresh_claude_token(core.Path("/x/.credentials.json")), "new")
        self.assertIn("could not write", err.getvalue())
        core._claude_ua_cache = None


class CodexSubLimitLabelTests(unittest.TestCase):
    def test_sub_limit_windows_labeled_by_duration_not_slot(self):
        # primary_window here is a WEEKLY window (7d) — must not be labeled "5h".
        payload = {"email": "x@y.z", "plan_type": "pro", "rate_limit": {},
                   "additional_rate_limits": [{
                       "limit_name": "Spark",
                       "rate_limit": {
                           "primary_window":   {"used_percent": 5, "limit_window_seconds": 604800},
                           "secondary_window": {"used_percent": 7, "limit_window_seconds": 18000},
                       }}]}
        with patch("cli_usage_core.shutil.which", return_value="/usr/bin/codex"), \
             patch("cli_usage_core.Path.exists", return_value=True), \
             patch("cli_usage_core.Path.read_text",
                   return_value=json.dumps({"tokens": {"access_token": "t"}})), \
             patch("cli_usage_core._http_json", return_value=payload):
            rows = [r[0] for r in core.codex_data()["rows"]]
        sub = [r for r in rows if "% left" in r]
        self.assertEqual(len(sub), 2)
        self.assertIn("Weekly", sub[0])   # 604800s → Weekly, even though it's primary
        self.assertIn("5h", sub[1])       # 18000s  → 5h, even though it's secondary


if __name__ == "__main__":
    unittest.main()
