"""Read a Thunderbird installation's preference defaults, for the tests that must
cross-check the plugin's prefs against the real thing.

Two checks need this: profile/user.js (a pref equal to the default is dropped and does
nothing) and bin/policies.json (a policy pref that is not a real Thunderbird pref is
silently ignored). Both want the same answer — "does Thunderbird actually know this
pref?" — so the scraper lives here and each test imports it.

Everything is skipped, with a notice, when Thunderbird is not installed.
"""

import json
import pathlib
import re
import zipfile

OMNI_CANDIDATES = [
    pathlib.Path("/usr/lib/thunderbird/omni.ja"),
    pathlib.Path("/usr/share/thunderbird/omni.ja"),
]

POLICY_SCHEMA_MEMBER = "modules/policies/policies-schema.json"

# A pref declared with a built-in default: pref("name", value);
DEFAULT_PAIR = re.compile(r'pref\(\s*"([^"]+)"\s*,\s*([^;\n]*?)\s*\)')
# Any pref-shaped quoted string, so a pref read without a declared default still counts
# as real. Segments may contain a hyphen (layout.css.prefers-color-scheme.content-override).
PREF_LIKE = re.compile(r'"([a-z][A-Za-z0-9_-]{2,}(?:\.[A-Za-z0-9_-]+)+)"')


def literal(raw):
    """The Python value of a pref literal as it appears in Thunderbird's source."""
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    match = re.fullmatch(r'"(.*)"|\'(.*)\'', raw)
    if match:
        return match.group(1) if match.group(1) is not None else match.group(2)
    return raw


def thunderbird_policy_schema():
    """The set of enterprise-policy names the installed Thunderbird accepts, else None.

    Thunderbird validates distribution/policies.json against this schema; a policy
    name absent from it has no handler and is silently ignored.
    """
    omni = next((p for p in OMNI_CANDIDATES if p.is_file()), None)
    if omni is None:
        return None
    with zipfile.ZipFile(omni) as archive:
        try:
            body = archive.read(POLICY_SCHEMA_MEMBER).decode("utf-8", "replace")
        except (KeyError, OSError):
            return None
    return set(json.loads(body).get("properties", {}))


def thunderbird_prefs():
    """(defaults, referenced) scraped from the installed Thunderbird, else None.

    `defaults` maps a pref to its built-in default value (from `pref("k", v)`).
    `referenced` is every pref-like quoted string in the shipped JS — a pref
    Thunderbird reads via getBoolPref() without declaring a default is real but
    absent from `defaults`, so realness is the union of the two.
    """
    omni = next((p for p in OMNI_CANDIDATES if p.is_file()), None)
    if omni is None:
        return None
    defaults = {}
    referenced = set()
    with zipfile.ZipFile(omni) as archive:
        for name in archive.namelist():
            if not name.endswith((".js", ".mjs")):
                continue
            try:
                body = archive.read(name).decode("utf-8", "replace")
            except (KeyError, OSError):
                continue
            for key, raw in DEFAULT_PAIR.findall(body):
                if key not in defaults and not key.startswith("_"):
                    defaults[key] = literal(raw)
            referenced.update(PREF_LIKE.findall(body))
    return defaults, referenced
