#!/bin/bash
# e2e: the guard extension is packaged and loads in a real Thunderbird.
#
# Static checks cannot prove an extension manifest is one Thunderbird will accept.
# This boot a real headless Thunderbird with the built .xpi sideloaded into the
# profile and asserts the add-on registered and is active — the only honest proof the
# manifest, background scripts and permissions are right.
set -u
source "$(dirname "$(readlink -f "$0")")/lib.sh"

GECKO_ID="guard@omarchy-thunderbird.maximilian-maag"

if ! command -v thunderbird >/dev/null 2>&1; then
  echo "test_extension_load.sh: SKIP (no thunderbird binary in PATH)"
  exit 0
fi

work="$(mktemp -d)"
trap 'e2e_tb_stop "${tb_pid:-}"; rm -rf "$work"' EXIT

ROOT="$work/root"
REL="e2e.default-release"
e2e_mkprofile "$ROOT" "$REL"
PROFILE="$ROOT/thunderbird/$REL"

# 1. the applier writes the signing prefs the extension needs
XDG_CONFIG_HOME="$ROOT" python3 "$E2E_REPO/bin/omarchy-thunderbird-apply" --profile "$PROFILE" >/dev/null 2>&1
assert_contains "apply: signing disabled in user.js" \
  'user_pref("xpinstall.signatures.required", false);' "$PROFILE/user.js"

# 2. build and install the xpi into the profile
XDG_CONFIG_HOME="$ROOT" python3 "$E2E_REPO/bin/omarchy-thunderbird-xpi" --install \
  --out "$work/guard.xpi" >/dev/null 2>&1
assert_file "xpi installed into the profile" "$PROFILE/extensions/$GECKO_ID.xpi"

# 3. a real Thunderbird loads it
tb_pid="$(e2e_tb_start "$ROOT" "$PROFILE" 40)"
sleep 3
if [[ -f "$PROFILE/extensions.json" ]]; then
  python3 - "$PROFILE/extensions.json" "$GECKO_ID" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
addons = data.get("addons", data) if isinstance(data, dict) else data
want = sys.argv[2]
for addon in addons:
    if addon.get("id") == want:
        ok = addon.get("active") is True
        print("  %s extension %s loaded (active=%s)" % ("ok  " if ok else "FAIL", want, addon.get("active")))
        sys.exit(0 if ok else 1)
print("  FAIL extension %s not registered" % want)
sys.exit(1)
PY
  (( $? == 0 )) || fails=$((fails + 1))
  assert_contains "prefs.js records the extension uuid" "$GECKO_ID" "$PROFILE/prefs.js"
else
  bad "Thunderbird produced extensions.json"
fi

e2e_finish "test_extension_load.sh"
