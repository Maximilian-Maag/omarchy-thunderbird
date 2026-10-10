#!/bin/bash
# Shared helpers for the e2e tests.
#
# The e2e kind is the top of the ladder: it exercises the real shipped artifacts
# (hooks, profile assets, the reload CLI, the unread backend) against a REAL,
# throwaway Thunderbird profile — and, where it matters, against a real headless
# Thunderbird process. Every path here is derived from a temporary directory; the
# user's live profile and desktop session are never touched.
#
# Sourced, not executed: `source "$(dirname "$0")/lib.sh"`.

set -u

E2E_REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"

fails=0
ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }
assert_eq() { # assert_eq <desc> <want> <got>
  if [[ $2 == $3 ]]; then ok "$1"; else bad "$1 (want [$2] got [$3])"; fi
}
assert_contains() { # assert_contains <desc> <needle> <file>
  if grep -qF -- "$2" "$3" 2>/dev/null; then ok "$1"; else bad "$1 (missing: $2 in $3)"; fi
}
assert_file() { # assert_file <desc> <path>
  if [[ -f $2 ]]; then ok "$1"; else bad "$1 (no file: $2)"; fi
}

# e2e_mkprofile <root> <profile-path> [create=yes]
# Writes a minimal profiles.ini under <root>/thunderbird and optionally the dir.
e2e_mkprofile() {
  local root="$1" p="$2" create="${3:-yes}"
  mkdir -p "$root/thunderbird"
  printf '[Profile0]\nName=e2e\nPath=%s\nDefault=1\nIsRelative=1\n' "$p" \
    > "$root/thunderbird/profiles.ini"
  [[ $create == yes ]] && mkdir -p "$root/thunderbird/$p"
  return 0
}

# e2e_tb_start <root> <profile-path> <wait-seconds>
# Starts headless Thunderbird in its own session against the throwaway profile and
# waits until prefs.js materialises. Prints the pid on success, empty on timeout.
e2e_tb_start() {
  local root="$1" profile="$2" wait="${3:-30}"
  XDG_CONFIG_HOME="$root" HOME="$root" setsid thunderbird --headless --profile "$profile" \
    >"$root/tb.log" 2>&1 &
  local pid=$!
  local i=0
  while (( i < wait * 4 )); do
    [[ -f "$profile/prefs.js" ]] && { sleep 1; printf '%s' "$pid"; return 0; }
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25; i=$((i + 1))
  done
  printf '%s' "$pid"
  return 1
}

# e2e_tb_stop <pid>
e2e_tb_stop() {
  local pid="${1:-}"
  [[ -n $pid ]] || return 0
  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  sleep 0.5
  kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

# e2e_finish <test-name>
e2e_finish() {
  printf '\n'
  if (( fails == 0 )); then
    echo "$1: all assertions passed"
    exit 0
  fi
  echo "$1: $fails assertion(s) failed"
  exit 1
}
