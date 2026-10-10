#!/bin/bash
# e2e: install the shipped profile assets into a throwaway profile, then hand that
# profile to a REAL headless Thunderbird and assert the prefs actually took.
#
# This is the difference between "the file looks right" (unit/js) and "Thunderbird
# accepted it": only a real process parsing user.js and writing prefs.js proves the
# profile wiring works end to end. The theme hook and the userChrome.css symlink are
# exercised on the same profile the app then boots against.
#
# Skips (exit 0 with a notice) only when no thunderbird binary exists — CI installs
# it, so the skip cannot hide a regression there.
set -u
source "$(dirname "$(readlink -f "$0")")/lib.sh"

if ! command -v thunderbird >/dev/null 2>&1; then
  echo "test_profile_install.sh: SKIP (no thunderbird binary in PATH)"
  exit 0
fi

work="$(mktemp -d)"
trap 'e2e_tb_stop "${tb_pid:-}"; rm -rf "$work"' EXIT

PROFILE_REL="e2e.default-release"
ROOT="$work/root"
e2e_mkprofile "$ROOT" "$PROFILE_REL"
PROFILE="$ROOT/thunderbird/$PROFILE_REL"
CHROME="$PROFILE/chrome"

# ── 1. the theme-set hook writes the slug + helper into the real profile ─────
XDG_CONFIG_HOME="$ROOT" bash "$E2E_REPO/hooks/theme-set" "Tokyo Night" >/dev/null 2>&1
assert_eq "hook: slugged state file" "tokyo-night" "$(cat "$CHROME/omarchy-active-theme" 2>/dev/null)"
assert_file "hook: helper script present" "$CHROME/set-theme.uc.js"

# ── 2. the hook rendered the applied stylesheet into the profile ─────────────
# The theme is inlined into the :root block, so no loader is needed and no symlink
# is involved: chrome/userChrome.css is a real, self-contained stylesheet.
assert_file "install: userChrome.css rendered into the profile" "$CHROME/userChrome.css"
assert_contains "install: userChrome.css is themed (tokyo-night)" \
  'applied theme = tokyo-night' "$CHROME/userChrome.css"
assert_contains "install: the active theme's variables are inlined" \
  '--toolbar-bgcolor: #1a1b26;' "$CHROME/userChrome.css"
assert_file "install: userContent.css rendered (message body)" "$CHROME/userContent.css"
assert_contains "install: message body follows the theme" \
  '--tb-bg: #1a1b26;' "$CHROME/userContent.css"

# ── 3. user.js is merged into the profile (as install.sh does) ───────────────
cp "$E2E_REPO/profile/user.js" "$PROFILE/user.js"

# ── 4. a real headless Thunderbird boots on this profile and persists prefs ──
tb_pid="$(e2e_tb_start "$ROOT" "$PROFILE" 40)"
if [[ -n $tb_pid ]] && [[ -f "$PROFILE/prefs.js" ]]; then
  ok "e2e: headless Thunderbird created prefs.js"

  # The stylesheets pref is the one that makes userChrome.css theming work at all.
  # Thunderbird only materialises a pref into prefs.js when its value DIFFERS from
  # the built-in default, so every assertion here targets a non-default pref — the
  # ones that equal a default are (correctly) absent from the file.
  assert_contains "prefs.js: userChrome theming enabled" \
    'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' "$PROFILE/prefs.js"
  # Telemetry/studies off, both non-default.
  assert_contains "prefs.js: normandy studies disabled" \
    'user_pref("app.normandy.enabled", false);' "$PROFILE/prefs.js"
  assert_contains "prefs.js: crash-report nag disabled" \
    'user_pref("browser.crashReports.unsubmittedCheck.enabled", false);' "$PROFILE/prefs.js"
  # A non-boolean value, to show typed values survive the round-trip.
  assert_contains "prefs.js: crash reporter URL blanked" \
    'user_pref("breakpad.reportURL", "");' "$PROFILE/prefs.js"
  # The notification / identity prefs added by this plugin must also survive a real
  # boot — they are the point of the feature, so their absence is a real failure.
  assert_contains "prefs.js: new-mail sound silenced" \
    'user_pref("mail.biff.play_sound", false);' "$PROFILE/prefs.js"
  assert_contains "prefs.js: external GnuPG allowed for OpenPGP" \
    'user_pref("mail.openpgp.allow_external_gnupg", true);' "$PROFILE/prefs.js"
  assert_contains "prefs.js: start page disabled" \
    'user_pref("mailnews.start_page.enabled", false);' "$PROFILE/prefs.js"

  # A booted Thunderbird also persists prefs of its own; extensions.lastAppVersion
  # is written on every real startup and never by us, so its presence proves the
  # profile is a genuine Thunderbird export rather than a stub we fabricated.
  assert_contains "e2e: profile is a real Thunderbird boot" \
    'user_pref("extensions.lastAppVersion"' "$PROFILE/prefs.js"
else
  bad "e2e: headless Thunderbird created prefs.js (pid=[$tb_pid])"
fi

e2e_finish "test_profile_install.sh"
