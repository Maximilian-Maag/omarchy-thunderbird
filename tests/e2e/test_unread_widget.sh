#!/bin/bash
# e2e: the unread-count backend against a real Thunderbird profile.
#
# Two layers. First a synthetic profile so the count is a known, exact number the
# backend must reproduce through its full CLI. Then a real headless Thunderbird boot
# on the same profile, to prove the backend still works against a profile the
# application itself has touched — which is what the bar widget polls in practice.
set -u
source "$(dirname "$(readlink -f "$0")")/lib.sh"

UNREAD="$E2E_REPO/bin/omarchy-thunderbird-unread"

work="$(mktemp -d)"
trap 'e2e_tb_stop "${tb_pid:-}"; rm -rf "$work"' EXIT

ROOT="$work/root"
REL="e2e.default-release"
e2e_mkprofile "$ROOT" "$REL"
PROFILE="$ROOT/thunderbird/$REL"

# ── 1. a synthetic mbox: 2 unread, 1 read ────────────────────────────────────
mkdir -p "$PROFILE/Mail/Local Folders"
cat > "$PROFILE/Mail/Local Folders/Inbox" <<'MBOX'
From a@example.com Thu Jan  1 00:00:00 2026
X-Mozilla-Status: 0000
X-Mozilla-Status2: 00000000
Subject: fresh

one

From b@example.com Thu Jan  1 00:00:00 2026
X-Mozilla-Status: 0000
X-Mozilla-Status2: 00000000
Subject: newer

two

From c@example.com Thu Jan  1 00:00:00 2026
X-Mozilla-Status: 0001
X-Mozilla-Status2: 00000000
Subject: old

three
MBOX

count="$(XDG_CONFIG_HOME="$ROOT" "$UNREAD" 2>/dev/null)"
assert_eq "backend counts unread mail through its CLI" "2" "$count"

json="$(XDG_CONFIG_HOME="$ROOT" "$UNREAD" --json 2>/dev/null)"
if printf '%s' "$json" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["unread"] == 2' 2>/dev/null; then
  ok "backend --json is parseable and agrees"
else
  bad "backend --json is parseable and agrees"
fi

# ── 1b. calendar backend against a seeded calendar store ─────────────────────
mkdir -p "$PROFILE/calendar-data"
python3 - "$PROFILE/calendar-data/local.sqlite" <<'PY'
import datetime, sqlite3, sys
start = datetime.datetime.now() + datetime.timedelta(hours=3)
us = int(start.timestamp()) * 1000000
c = sqlite3.connect(sys.argv[1])
c.execute("CREATE TABLE cal_events (id TEXT, cal_id TEXT, title TEXT, event_start INTEGER, event_end INTEGER, ical_status TEXT)")
c.execute("INSERT INTO cal_events VALUES (?,?,?,?,?,?)",
          ("1", "cal", "Dentist", us, us + 3600 * 1000000, "CONFIRMED"))
c.commit(); c.close()
PY
count="$(XDG_CONFIG_HOME="$ROOT" "$E2E_REPO/bin/omarchy-thunderbird-calendar" --count 2>/dev/null)"
assert_eq "calendar backend counts the seeded event" "1" "$count"
if XDG_CONFIG_HOME="$ROOT" "$E2E_REPO/bin/omarchy-thunderbird-calendar" --json 2>/dev/null \
   | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["events"][0]["title"] == "Dentist"' 2>/dev/null; then
  ok "calendar backend --json names the event"
else
  bad "calendar backend --json names the event"
fi

# ── 1c. chat backend runs against a real profile ─────────────────────────────
if XDG_CONFIG_HOME="$ROOT" "$E2E_REPO/bin/omarchy-thunderbird-chat" --json 2>/dev/null \
   | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "accounts" in d' 2>/dev/null; then
  ok "chat backend reports account shape"
else
  bad "chat backend reports account shape"
fi

# ── 2. a REAL Thunderbird boot on the same profile ───────────────────────────
if command -v thunderbird >/dev/null 2>&1; then
  tb_pid="$(e2e_tb_start "$ROOT" "$PROFILE" 40)"
  if [[ -f "$PROFILE/prefs.js" ]]; then
    ok "e2e: real Thunderbird booted on the widget's profile"
    after="$(XDG_CONFIG_HOME="$ROOT" "$UNREAD" 2>/dev/null)"
    if [[ $after =~ ^[0-9]+$ ]]; then
      ok "backend returns an integer on a real profile ($after)"
    else
      bad "backend returns an integer on a real profile (got [$after])"
    fi
  else
    bad "e2e: real Thunderbird booted on the widget's profile"
  fi
else
  echo "  skip e2e: no thunderbird binary in PATH"
fi

e2e_finish "test_unread_widget.sh"
