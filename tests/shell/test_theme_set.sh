#!/bin/bash
# Shell tests for hooks/theme-set.
#
# The hook is what Omarchy calls on every `omarchy theme set`: it slugs the theme
# name and writes it into the Thunderbird profile that will actually be read. These
# assertions run the real hook under a temporary XDG_CONFIG_HOME with a synthetic
# profiles.ini, so they never touch the user's live profile. They are also the tests
# the mutation pass relies on for hooks/theme-set.
set -u

REPO="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
HOOK="$REPO/hooks/theme-set"
fails=0

ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }
assert_eq() { # assert_eq <desc> <want> <got>
  if [[ $2 == $3 ]]; then ok "$1"; else bad "$1 (want [$2] got [$3])"; fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

make_profile() { # make_profile <root> <profile-path> [create]
  local root="$1" p="$2" create="${3:-yes}"
  mkdir -p "$root/thunderbird"
  printf '[Profile0]\nName=default\nPath=%s\nDefault=1\nIsRelative=1\n' "$p" \
    > "$root/thunderbird/profiles.ini"
  [[ $create == yes ]] && mkdir -p "$root/thunderbird/$p"
  return 0
}

run_hook() { # run_hook <root> [theme...] -> prints exit status
  local root="$1"; shift
  XDG_CONFIG_HOME="$root" bash "$HOOK" "$@" >/dev/null 2>&1
  printf '%s' "$?"
}

# ── 1. an empty theme name is a no-op: nothing written, exit 0 ───────────────
a="$work/a"
make_profile "$a" "abc.default-release"
rc=$(run_hook "$a")
assert_eq "empty theme: exit status" 0 "$rc"
state="$a/thunderbird/abc.default-release/chrome/omarchy-active-theme"
if [[ -e $state ]]; then bad "empty theme: no state file written"; else ok "empty theme: no state file written"; fi

# ── 2. a real theme is slugified into the default-release profile ────────────
rc=$(run_hook "$a" "Tokyo Night")
assert_eq "theme set: exit status" 0 "$rc"
assert_eq "theme set: slug in state file" "tokyo-night" "$(cat "$state" 2>/dev/null)"

helper="$a/thunderbird/abc.default-release/chrome/set-theme.uc.js"
if [[ -f $helper ]]; then ok "theme set: helper script written"; else bad "theme set: helper script written"; fi
if grep -q 'const theme = "tokyo-night";' "$helper" 2>/dev/null; then
  ok "theme set: helper carries the slug"
else
  bad "theme set: helper carries the slug"
fi

# ── 2b. the applied stylesheet is rendered with the theme inlined into :root ──
css="$a/thunderbird/abc.default-release/chrome/userChrome.css"
if [[ -f $css ]]; then ok "theme set: userChrome.css rendered"; else bad "theme set: userChrome.css rendered"; fi
if grep -q 'applied theme = tokyo-night' "$css" 2>/dev/null; then
  ok "theme set: rendered css names the applied theme"
else
  bad "theme set: rendered css names the applied theme"
fi
if grep -q -- '--toolbar-bgcolor: #1a1b26;' "$css" 2>/dev/null; then
  ok "theme set: rendered css inlines the theme's variables"
else
  bad "theme set: rendered css inlines the theme's variables"
fi

content="$a/thunderbird/abc.default-release/chrome/userContent.css"
if [[ -f $content ]] && grep -q -- '--tb-bg: #1a1b26;' "$content" 2>/dev/null; then
  ok "theme set: message body stylesheet rendered from the theme"
else
  bad "theme set: message body stylesheet rendered from the theme"
fi

# ── 2c. an unknown theme keeps the bundled fallback and still renders ─────────
rc=$(run_hook "$a" "no-such-theme")
assert_eq "unknown theme: exit status" 0 "$rc"
if grep -q 'applied theme = catppuccin (fallback)' "$css" 2>/dev/null; then
  ok "unknown theme: falls back to the bundled palette"
else
  bad "unknown theme: falls back to the bundled palette"
fi

# ── 3. no usable profile directory: exit 0 and create nothing ────────────────
b="$work/b"
make_profile "$b" "ghost-profile" no
rc=$(run_hook "$b" "gruvbox")
assert_eq "missing profile dir: exit status" 0 "$rc"
if [[ -e "$b/thunderbird/ghost-profile" ]]; then
  bad "missing profile dir: directory not created"
else
  ok "missing profile dir: directory not created"
fi

# ── 4. profile detection prefers default-release over a plain default ────────
c="$work/c"
mkdir -p "$c/thunderbird/plain.default" "$c/thunderbird/sel.default-release"
printf '[Profile0]\nName=plain\nPath=plain.default\nDefault=1\nIsRelative=1\n' \
  > "$c/thunderbird/profiles.ini"
printf '[Profile1]\nName=release\nPath=sel.default-release\nDefault=0\nIsRelative=1\n' \
  >> "$c/thunderbird/profiles.ini"
rc=$(run_hook "$c" "nord")
assert_eq "default-release preferred: exit status" 0 "$rc"
if [[ -f "$c/thunderbird/sel.default-release/chrome/omarchy-active-theme" ]]; then
  ok "default-release preferred over Default=1"
else
  bad "default-release preferred over Default=1"
fi

# ── 4. no profiles.ini at all: the hook still exits 0 and creates nothing ────
d="$work/d"
mkdir -p "$d/thunderbird"
rc=$(run_hook "$d" "nord")
assert_eq "no profiles.ini: exit status" 0 "$rc"
if [[ -e "$d/thunderbird/chrome" ]]; then
  bad "no profiles.ini: nothing created"
else
  ok "no profiles.ini: nothing created"
fi

printf '\n'
if (( fails == 0 )); then
  echo "test_theme_set.sh: all assertions passed"
  exit 0
fi
echo "test_theme_set.sh: $fails assertion(s) failed"
exit 1
