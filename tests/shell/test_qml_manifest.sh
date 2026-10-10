#!/bin/bash
# Shell tests: the bar widget (shell/BarWidget.qml) and its manifest wiring.
#
# The widget cannot be instantiated headlessly without a running Omarchy shell, but
# two things can be checked honestly: that it is valid QML (qmllint) and that the
# manifest exposes it as a bar widget the shell can discover. Both are pinned here so
# a broken widget or a missing entryPoint fails the suite instead of shipping.
set -u

REPO="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
QML="$REPO/shell/BarWidget.qml"
MANIFEST="$REPO/manifest.json"
fails=0

ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

# ── 1. the widget is valid QML ───────────────────────────────────────────────
QMLLINT="$(command -v qmllint || true)"
[[ -z $QMLLINT && -x /usr/lib/qt6/bin/qmllint ]] && QMLLINT=/usr/lib/qt6/bin/qmllint
if [[ -n $QMLLINT ]]; then
  out="$("$QMLLINT" "$QML" 2>&1)"; rc=$?
  if (( rc == 0 )) && ! grep -q "Error:" <<< "$out"; then
    ok "qmllint: BarWidget.qml is valid QML"
  else
    bad "qmllint: BarWidget.qml is valid QML (rc=$rc)"
    printf '%s\n' "$out" | head -20
  fi
else
  echo "  skip qmllint: not installed"
fi

# ── 2. the widget drives the unread backend and polls it ─────────────────────
if grep -qF 'omarchy-thunderbird-unread' "$QML"; then
  ok "widget calls the unread backend"
else
  bad "widget calls the unread backend"
fi
if grep -qF 'Quickshell.Io' "$QML" && grep -qF 'Process {' "$QML"; then
  ok "widget polls via a Quickshell Process"
else
  bad "widget polls via a Quickshell Process"
fi

# ── 3. the manifest exposes the widget to the shell ──────────────────────────
python3 - "$MANIFEST" "$REPO" <<'PY'
import json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
repo = pathlib.Path(sys.argv[2])
problems = []
if "bar-widget" not in manifest.get("kinds", []):
    problems.append("kinds does not include bar-widget")
ep = manifest.get("entryPoints", {}).get("barWidget")
if ep != "shell/BarWidget.qml":
    problems.append("entryPoints.barWidget is %r" % ep)
elif not (repo / ep).is_file():
    problems.append("entryPoints.barWidget points at a missing file: %s" % ep)
if not isinstance(manifest.get("barWidget"), dict) or not manifest["barWidget"].get("displayName"):
    problems.append("barWidget metadata (displayName) is missing")
if problems:
    print("  FAIL manifest: " + "; ".join(problems))
    sys.exit(1)
print("  ok   manifest exposes shell/BarWidget.qml as a bar widget")
PY
(( $? == 0 )) || fails=$((fails + 1))

printf '\n'
if (( fails == 0 )); then
  echo "test_qml_manifest.sh: all assertions passed"
  exit 0
fi
echo "test_qml_manifest.sh: $fails assertion(s) failed"
exit 1
