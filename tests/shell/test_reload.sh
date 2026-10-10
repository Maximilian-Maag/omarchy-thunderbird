#!/bin/bash
# Shell tests for bin/omarchy-thunderbird-reload.
#
# The reload CLI restarts Thunderbird, which must never happen against a real running
# mail client during a test. So pgrep/pkill/setsid are stubbed on PATH: the test
# asserts the CLI *decides* to restart and calls those tools, without touching any
# process on the machine.
set -u

REPO="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
RELOAD="$REPO/bin/omarchy-thunderbird-reload"
fails=0

ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }
assert_eq() { if [[ $2 == $3 ]]; then ok "$1"; else bad "$1 (want [$2] got [$3])"; fi; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

make_profile() { # make_profile <root>
  local root="$1"
  mkdir -p "$root/thunderbird/abc.default-release"
  printf '[Profile0]\nName=default\nPath=abc.default-release\nDefault=1\nIsRelative=1\n' \
    > "$root/thunderbird/profiles.ini"
}

# Stub tools: pgrep returns "running" the first time (0) then "stopped" (1), so the
# restart branch is entered and its wait loop exits immediately.
make_stubs() { # make_stubs <stubdir> <pgrep-exit>
  local dir="$1" pgrep_rc="$2"
  mkdir -p "$dir"
  cat > "$dir/pgrep" <<EOF
#!/bin/bash
c="\$dir/._pgrep_count"
n=\$(cat "\$c" 2>/dev/null || echo 0)
echo \$((n + 1)) > "\$c"
if [[ $pgrep_rc == running ]] && (( \$n == 0 )); then exit 0; fi
exit 1
EOF
  cat > "$dir/pkill" <<EOF
#!/bin/bash
echo "\$*" >> "$dir/._pkill"
exit 0
EOF
  cat > "$dir/setsid" <<EOF
#!/bin/bash
echo "\$*" >> "$dir/._setsid"
exit 0
EOF
  chmod +x "$dir/pgrep" "$dir/pkill" "$dir/setsid"
}

# ── 1. reload applies the stylesheet and restarts a running Thunderbird ──────
a="$work/a"; make_profile "$a"; make_stubs "$work/stub-run" running
PATH="$work/stub-run:$PATH" XDG_CONFIG_HOME="$a" bash "$RELOAD" "tokyo-night" >/dev/null 2>&1
assert_eq "restart path: exit status" 0 "$?"
css="$a/thunderbird/abc.default-release/chrome/userChrome.css"
if grep -q 'applied theme = tokyo-night' "$css" 2>/dev/null; then
  ok "reload: rendered the requested theme"
else
  bad "reload: rendered the requested theme"
fi
assert_eq "reload: recorded active theme" "tokyo-night" \
  "$(cat "$a/thunderbird/abc.default-release/chrome/omarchy-active-theme" 2>/dev/null)"
if grep -q -- '--tb-bg: #1a1b26;' "$a/thunderbird/abc.default-release/chrome/userContent.css" 2>/dev/null; then
  ok "reload: rendered the message body stylesheet"
else
  bad "reload: rendered the message body stylesheet"
fi
if [[ -s "$work/stub-run/._pkill" ]]; then ok "reload: sent SIGTERM to Thunderbird"; else bad "reload: sent SIGTERM to Thunderbird"; fi
if [[ -s "$work/stub-run/._setsid" ]]; then ok "reload: relaunched Thunderbird"; else bad "reload: relaunched Thunderbird"; fi

# ── 2. reload applies without restarting when Thunderbird is not running ─────
b="$work/b"; make_profile "$b"; make_stubs "$work/stub-stop" stopped
PATH="$work/stub-stop:$PATH" XDG_CONFIG_HOME="$b" bash "$RELOAD" "nord" >/dev/null 2>&1
assert_eq "not-running path: exit status" 0 "$?"
cssb="$b/thunderbird/abc.default-release/chrome/userChrome.css"
if grep -q 'applied theme = nord' "$cssb" 2>/dev/null; then
  ok "reload: still applied the theme when not running"
else
  bad "reload: still applied the theme when not running"
fi
if [[ -e "$work/stub-stop/._pkill" ]]; then bad "reload: did NOT signal when not running"; else ok "reload: did NOT signal when not running"; fi
if [[ -e "$work/stub-stop/._setsid" ]]; then bad "reload: did NOT relaunch when not running"; else ok "reload: did NOT relaunch when not running"; fi

# ── 3. no profile: reload fails loudly (exit 1) ──────────────────────────────
c="$work/c"; mkdir -p "$c/thunderbird"
PATH="$work/stub-stop:$PATH" XDG_CONFIG_HOME="$c" bash "$RELOAD" "nord" >/dev/null 2>&1
assert_eq "no profile: exit status" 1 "$?"

# ── 4. profiles.ini points at a missing dir: fail, and create nothing ────────
d="$work/d"; mkdir -p "$d/thunderbird"
printf '[Profile0]\nName=x\nPath=ghost.profile\nDefault=1\nIsRelative=1\n' \
  > "$d/thunderbird/profiles.ini"
PATH="$work/stub-stop:$PATH" XDG_CONFIG_HOME="$d" bash "$RELOAD" "nord" >/dev/null 2>&1
assert_eq "missing profile dir: exit status" 1 "$?"
if [[ -e "$d/thunderbird/ghost.profile" ]]; then
  bad "missing profile dir: nothing created"
else
  ok "missing profile dir: nothing created"
fi

# ── 5. theme precedence: the recorded theme is used when no arg is given ─────
e="$work/e"; make_profile "$e"
mkdir -p "$e/thunderbird/abc.default-release/chrome"
printf 'gruvbox\n' > "$e/thunderbird/abc.default-release/chrome/omarchy-active-theme"
PATH="$work/stub-stop:$PATH" XDG_CONFIG_HOME="$e" bash "$RELOAD" >/dev/null 2>&1
assert_eq "precedence: exit status" 0 "$?"
if grep -q 'applied theme = gruvbox' \
     "$e/thunderbird/abc.default-release/chrome/userChrome.css" 2>/dev/null; then
  ok "precedence: uses the recorded theme when no arg is given"
else
  bad "precedence: uses the recorded theme when no arg is given"
fi

# ── 6. an explicit argument overrides the recorded theme ─────────────────────
PATH="$work/stub-stop:$PATH" XDG_CONFIG_HOME="$e" bash "$RELOAD" "nord" >/dev/null 2>&1
if grep -q 'applied theme = nord' \
     "$e/thunderbird/abc.default-release/chrome/userChrome.css" 2>/dev/null; then
  ok "precedence: an explicit argument wins"
else
  bad "precedence: an explicit argument wins"
fi

printf '\n'
if (( fails == 0 )); then
  echo "test_reload.sh: all assertions passed"
  exit 0
fi
echo "test_reload.sh: $fails assertion(s) failed"
exit 1
