"""Shared, GUI-free data layer for the AI CLI tray indicator.

Works on Linux, macOS, and Windows. Used by both the GTK and pystray frontends.
"""

import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

CODEX_USAGE_URL = "https://chatgpt.com/backend-api/codex/usage"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
# Public OAuth client id of the Codex CLI (from its `codex login` URL). Used to
# refresh an expired access token from the stored refresh token, like the CLI.
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
# Public OAuth client id of Claude Code, used the same way for its token.
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Short tray tags per provider (shared by both frontends).
PROVIDER_TAGS = {"Claude Code": "CC", "Codex CLI": "CX"}

BAR_WIDTH   = 12
NET_TIMEOUT = 6
NET_RETRIES = 3
NET_BACKOFF = 0.6


def _bar(remaining_pct):
    if remaining_pct is None:
        return ""
    r = max(0.0, min(100.0, float(remaining_pct)))
    filled = round(r / 100 * BAR_WIDTH)
    return f"[{'█'*filled}{'░'*(BAR_WIDTH-filled)}] {int(round(r))}% left"


def _status_icon(remaining_pct):
    """Emoji color cue that works in most native tray menus.

    Native menu APIs do not consistently support arbitrary colored text, so we
    use portable colored icons in the label itself.
    """
    if remaining_pct is None:
        return "⚪"
    r = float(remaining_pct)
    if r < 10:
        return "🔴"
    if r < 30:
        return "🟡"
    return "🟢"


def _parse_when(when):
    if when in (None, "", 0):
        return None
    try:
        if isinstance(when, (int, float)):
            return datetime.fromtimestamp(float(when)).astimezone()
        return datetime.fromisoformat(str(when).replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def _reset_str(when, kind):
    dt = _parse_when(when)
    if not dt:
        return ""
    if kind == "5h":
        return f"resets {dt.strftime('%H:%M')}"
    day = dt.strftime("%d %b").lstrip("0")
    return f"resets {dt.strftime('%H:%M')} on {day}"


def _kv(key, val, key_w=10):
    return f"  {key:<{key_w}} {val}"


def _limit_row(label, used_pct, reset_when, kind, label_w=14):
    remaining = None if used_pct is None else 100 - float(used_pct)
    bar = _bar(remaining)
    rs  = _reset_str(reset_when, kind)
    tail = f"  ({rs})" if rs else ""
    return f"  {_status_icon(remaining)} {label:<{label_w}} {bar}{tail}"


class ProviderResponseError(ValueError):
    """Raised when a provider returns JSON in an unexpected shape."""


def _as_dict(value, name):
    if not isinstance(value, dict):
        raise ProviderResponseError(f"{name} response was not an object")
    return value


def _as_optional_dict(value, name):
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ProviderResponseError(f"{name} was not an object")
    return value


def _as_optional_list(value, name):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ProviderResponseError(f"{name} was not a list")
    return value


def _as_optional_number(value, name):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError(f"{name} was not numeric") from exc


def _http_json(url, headers, timeout=NET_TIMEOUT, retries=NET_RETRIES, backoff=NET_BACKOFF, data=None):
    req = urllib.request.Request(url, headers=headers, data=data)
    last_exc = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            last_exc = exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            should_retry = exc.code == 429 or 500 <= exc.code < 600
            try:
                exc.close()
            except Exception:
                pass
            if not should_retry or attempt == retries - 1:
                raise
            delay = float(retry_after) if retry_after and retry_after.isdigit() else backoff * (2 ** attempt)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))
    raise last_exc


def _atomic_write_json(path, obj):
    """Write JSON to `path` atomically, keeping 0600 perms (it holds tokens)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _refresh_oauth(token_url, client_id, refresh_token, scope=None, user_agent="cli-usage"):
    """POST a refresh_token grant; return the token response dict or None.

    retries=1 on purpose: providers rotate the refresh token, so re-POSTing a
    refresh could burn a second one. A realistic User-Agent is required:
    Anthropic's token endpoint sits behind a Cloudflare integrity check that
    answers a bare urllib UA with "403 error code: 1010" instead of OAuth JSON.
    """
    try:
        payload = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if scope:
            payload["scope"] = scope
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": user_agent}
        d = _http_json(token_url, headers, data=body, retries=1)
    except Exception:
        return None
    return d if isinstance(d, dict) and d.get("access_token") else None


def _remaining(used_pct):
    """Remaining percent from a used percent, or None if unknown."""
    return None if used_pct is None else 100 - float(used_pct)


def summary_worst(info):
    """Lowest remaining % across a provider's 5h/weekly windows, or None."""
    vals = [v for v in (info.get("summary") or {}).values() if v is not None]
    return min(vals) if vals else None


def summary_badge(tag, info):
    """Compact at-a-glance text for a provider, shared by both frontends.

    Both windows → "CC 86/32%" (5h/weekly, always that order);
    one window   → "CX 77%";
    no data / not installed → just the tag.
    """
    summary = info.get("summary") or {}
    five, week = summary.get("5h"), summary.get("weekly")
    present = [v for v in (five, week) if v is not None]
    if not info.get("installed") or not present:
        return tag
    if five is not None and week is not None:
        return f"{tag} {int(round(five))}/{int(round(week))}%"
    return f"{tag} {int(round(present[0]))}%"


def _codex_window_label(window, fallback="Limit", fallback_kind="week"):
    """Label + reset-kind for a Codex rate-limit window from its duration.

    Codex no longer guarantees primary_window is the 5h window and secondary
    the weekly one — on some plans primary_window IS the weekly window. Derive
    the label from limit_window_seconds instead of the slot position.
    """
    secs = window.get("limit_window_seconds")
    if not secs:
        return fallback, fallback_kind
    hours = secs / 3600
    if hours <= 6:
        return f"{int(round(hours))}h limit", "5h"
    days = secs / 86400
    if abs(days - 7) < 0.5:
        return "Weekly limit", "week"
    return f"{int(round(days))}d limit", "week"


def _usage_error_rows(exc, relogin_hint):
    """Menu rows for a failed usage fetch. 401 gets an explicit re-login hint."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return [(f"  ⚠ re-login required (run: {relogin_hint})", False, None)]
        return [(f"  usage unavailable (HTTP {exc.code})", False, None)]
    return [(f"  usage unavailable ({type(exc).__name__})", False, None)]


def validate_claude_usage(data):
    data = _as_dict(data, "Claude usage")
    for key in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
        window = _as_optional_dict(data.get(key), key)
        _as_optional_number(window.get("utilization"), f"{key}.utilization")
    # Per-model barometers (Fable, etc.) now live in the limits[] array.
    for i, lim in enumerate(_as_optional_list(data.get("limits"), "limits")):
        lim = _as_dict(lim, f"limits[{i}]")
        _as_optional_number(lim.get("percent"), f"limits[{i}].percent")
    extra = _as_optional_dict(data.get("extra_usage"), "extra_usage")
    _as_optional_number(extra.get("utilization"), "extra_usage.utilization")
    return data


def validate_codex_usage(data):
    data = _as_dict(data, "Codex usage")
    rl = _as_optional_dict(data.get("rate_limit"), "rate_limit")
    for name in ("primary_window", "secondary_window"):
        window = _as_optional_dict(rl.get(name), f"rate_limit.{name}")
        _as_optional_number(window.get("used_percent"), f"rate_limit.{name}.used_percent")
    for i, extra in enumerate(_as_optional_list(data.get("additional_rate_limits"), "additional_rate_limits")):
        extra = _as_dict(extra, f"additional_rate_limits[{i}]")
        erl = _as_optional_dict(extra.get("rate_limit"), f"additional_rate_limits[{i}].rate_limit")
        for name in ("primary_window", "secondary_window"):
            window = _as_optional_dict(erl.get(name), f"additional_rate_limits[{i}].rate_limit.{name}")
            _as_optional_number(window.get("used_percent"), f"additional_rate_limits[{i}].rate_limit.{name}.used_percent")
    _as_optional_dict(data.get("credits"), "credits")
    return data


# ── Claude Code ──────────────────────────────────────────────────────────────

def refresh_claude_token(creds_file):
    """Refresh an expired Claude Code access token from its stored refresh
    token and persist the result back to .credentials.json. Returns the new
    access token, or None if unavailable/failed. Mirrors refresh_codex_token so
    a ~expired token self-heals instead of showing "re-login required".
    """
    try:
        c = json.loads(creds_file.read_text())
    except Exception:
        return None
    o = c.get("claudeAiOauth") or {}
    rt = o.get("refreshToken")
    if not rt:
        return None
    d = _refresh_oauth(CLAUDE_TOKEN_URL, CLAUDE_OAUTH_CLIENT_ID, rt,
                       user_agent="claude-code/ai-tray")
    if not d:
        return None
    access = d["access_token"]
    o["accessToken"] = access
    if d.get("refresh_token"):          # rotated — persist the new one
        o["refreshToken"] = d["refresh_token"]
    if d.get("expires_in"):
        o["expiresAt"] = int((time.time() + float(d["expires_in"])) * 1000)
    c["claudeAiOauth"] = o
    try:
        _atomic_write_json(creds_file, c)
    except Exception:
        pass  # the token still works for this cycle
    return access


def _claude_usage(tok, creds_file):
    """Fetch Claude usage; on a 401 (expired token) refresh once and retry."""
    headers = {
        "Authorization":     f"Bearer {tok}",
        "anthropic-beta":    "oauth-2025-04-20",
        "anthropic-version": "2023-06-01",
        "User-Agent":        "claude-code/ai-tray",
    }
    try:
        return validate_claude_usage(_http_json(CLAUDE_USAGE_URL, headers))
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        new = refresh_claude_token(creds_file)
        if not new:
            raise
        headers["Authorization"] = f"Bearer {new}"
        return validate_claude_usage(_http_json(CLAUDE_USAGE_URL, headers))


def claude_data():
    rows = []
    summary = {"5h": None, "weekly": None}
    if not shutil.which("claude"):
        return {"installed": False, "rows": [("  not installed", False, None)], "summary": summary}

    dot = Path.home() / ".claude.json"
    email, billing = "", ""
    if dot.exists():
        try:
            d = json.loads(dot.read_text())
            oa = d.get("oauthAccount", {})
            email   = oa.get("emailAddress", "")
            billing = oa.get("billingType", "")
        except Exception:
            pass

    creds = Path.home() / ".claude" / ".credentials.json"
    tok, sub_type, tier = None, "", ""
    if creds.exists():
        try:
            c = json.loads(creds.read_text())
            o = c.get("claudeAiOauth", {})
            tok      = o.get("accessToken")
            sub_type = o.get("subscriptionType", "")
            tier     = o.get("rateLimitTier", "")
        except Exception:
            pass

    plan = (sub_type or billing or "").replace("_", " ").title() or "logged in"
    account_line = email + (f" ({plan})" if plan else "")
    rows.append((_kv("Account", account_line), False, None))
    if tier:
        rows.append((_kv("Tier", tier.replace("_", " ")), False, None))

    if tok:
        try:
            u = _claude_usage(tok, creds)
        except Exception as e:
            rows.extend(_usage_error_rows(e, "claude /login"))
            return {"installed": True, "rows": rows, "summary": summary}

        for label, key, kind, slot in [
            ("5h limit",     "five_hour", "5h",   "5h"),
            ("Weekly limit", "seven_day", "week", "weekly"),
        ]:
            w = u.get(key) or {}
            if w.get("utilization") is not None:
                summary[slot] = _remaining(w.get("utilization"))
                rows.append((_limit_row(label, w.get("utilization"),
                                        w.get("resets_at"), kind), False, None))

        # Per-model weekly barometers (Fable, Opus, Sonnet, …). Anthropic moved
        # these out of the dedicated seven_day_* fields into a generic limits[]
        # array keyed by scope.model.display_name, so this picks up new models
        # automatically.
        for lim in u.get("limits") or []:
            model = (lim.get("scope") or {}).get("model") or {}
            name  = model.get("display_name")
            if not name or lim.get("percent") is None:
                continue
            is_session = lim.get("group") == "session"
            label = f"{name} 5h" if is_session else f"Weekly {name}"
            rows.append((_limit_row(label, lim["percent"], lim.get("resets_at"),
                                    "5h" if is_session else "week"), False, None))

        eu = u.get("extra_usage") or {}
        if eu.get("is_enabled") and eu.get("utilization") is not None:
            rows.append((_limit_row("Extra usage", eu["utilization"], None, "week"), False, None))

    return {"installed": True, "rows": rows, "summary": summary}


# ── Codex CLI ────────────────────────────────────────────────────────────────

def refresh_codex_token(auth_file):
    """Refresh an expired Codex access token from the stored refresh token and
    persist the rotated tokens back to auth.json. Returns the new access token,
    or None if there is no refresh token or the refresh failed. This is what the
    Codex CLI does on its own; doing it here lets the tray self-heal an expired
    token instead of showing "re-login required" every ~10 days.
    """
    try:
        a = json.loads(auth_file.read_text())
    except Exception:
        return None
    rt = (a.get("tokens") or {}).get("refresh_token")
    if not rt:
        return None
    d = _refresh_oauth(CODEX_TOKEN_URL, CODEX_OAUTH_CLIENT_ID, rt,
                       scope="openid profile email offline_access",
                       user_agent="codex_cli_rs/ai-tray")
    if not d:
        return None
    access = d["access_token"]
    t = a.setdefault("tokens", {})
    t["access_token"] = access
    if d.get("id_token"):
        t["id_token"] = d["id_token"]
    if d.get("refresh_token"):          # rotated — must persist the new one
        t["refresh_token"] = d["refresh_token"]
    a["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z", time.gmtime())
    try:
        _atomic_write_json(auth_file, a)
    except Exception:
        pass  # even if persisting fails, the token works for this cycle
    return access


def _codex_usage(tok, auth_file):
    """Fetch Codex usage; on a 401 (expired token) refresh once and retry."""
    headers = {
        "Authorization": f"Bearer {tok}",
        "User-Agent": "codex_cli_rs/ai-tray",
        "originator": "codex_cli_rs",
    }
    try:
        return validate_codex_usage(_http_json(CODEX_USAGE_URL, headers))
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        new = refresh_codex_token(auth_file)
        if not new:
            raise
        headers["Authorization"] = f"Bearer {new}"
        return validate_codex_usage(_http_json(CODEX_USAGE_URL, headers))


def codex_data():
    rows = []
    summary = {"5h": None, "weekly": None}
    auth_file = Path.home() / ".codex" / "auth.json"
    # `codex` is often installed via nvm, whose bin dir is absent from a
    # systemd user service's PATH — so shutil.which() alone falsely reports
    # "not installed". The presence of ~/.codex/auth.json is an equally valid
    # signal (and it's what the usage fetch actually reads), so accept either.
    if not shutil.which("codex") and not auth_file.exists():
        return {"installed": False, "rows": [("  not installed", False, None)], "summary": summary}

    tok = None
    if auth_file.exists():
        try:
            a = json.loads(auth_file.read_text())
            t = a.get("tokens") or {}
            tok = t.get("access_token")
        except Exception:
            pass

    if not tok:
        rows.append(("  no auth token", False, None))
        return {"installed": True, "rows": rows, "summary": summary}

    try:
        u = _codex_usage(tok, auth_file)
    except Exception as e:
        rows.extend(_usage_error_rows(e, "codex login"))
        return {"installed": True, "rows": rows, "summary": summary}

    email = u.get("email", "")
    plan  = (u.get("plan_type") or "").title()
    rows.append((_kv("Account", email + (f" ({plan})" if plan else "")), False, None))

    rl = u.get("rate_limit") or {}
    for slot, fallback in (("primary_window", ("5h limit", "5h")),
                           ("secondary_window", ("Weekly limit", "week"))):
        w = rl.get(slot) or {}
        if w and w.get("used_percent") is not None:
            label, kind = _codex_window_label(w, *fallback)
            summary["5h" if kind == "5h" else "weekly"] = _remaining(w.get("used_percent"))
            rows.append((_limit_row(label, w.get("used_percent"),
                                    w.get("reset_at"), kind), False, None))

    # Per-model / metered sub-limits (e.g. GPT-5.3-Codex-Spark). Label each
    # window by its duration too — slot position is not a reliable indicator.
    for extra in (u.get("additional_rate_limits") or []):
        name = extra.get("limit_name") or extra.get("metered_feature") or "Extra"
        erl  = extra.get("rate_limit") or {}
        rows.append((f"  {name} limit:", False, None))
        for slot, fallback in (("primary_window", ("5h limit", "5h")),
                               ("secondary_window", ("Weekly limit", "week"))):
            w = erl.get(slot) or {}
            if w and w.get("used_percent") is not None:
                label, kind = _codex_window_label(w, *fallback)
                rows.append((_limit_row(f"  {label.replace(' limit', '')}",
                                        w.get("used_percent"), w.get("reset_at"), kind),
                             False, None))

    cr = u.get("credits") or {}
    if cr.get("has_credits") or cr.get("unlimited"):
        bal = cr.get("balance", "")
        rows.append((_kv("Credits", "unlimited" if cr.get("unlimited") else f"${bal}"), False, None))

    return {"installed": True, "rows": rows, "summary": summary}


def fetch_all():
    return {
        "Claude Code": claude_data(),
        "Codex CLI":   codex_data(),
    }


def worst_remaining_pct(data):
    """Lowest remaining % across every provider's 5h/weekly windows, from the
    structured `summary` (no re-parsing of formatted row text)."""
    vals = [summary_worst(info) for info in data.values() if isinstance(info, dict)]
    vals = [v for v in vals if v is not None]
    return int(round(min(vals))) if vals else None
