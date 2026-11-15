#!/bin/bash
# install.sh --uninstall, round-tripped in a throwaway tree.
#
# The installer writes outside the user's own config too, so its removal path has to reverse
# every one of those writes — and none of somebody else's. This test runs the *real*
# install.sh and then `--uninstall`, with the system locations pointed at a temp tree
# (OMARCHY_TB_*) and `sudo` stubbed to run in place, then asserts:
#   * the user's own hyprland.lua, autostart.lua and mimeapps.list are byte-identical (sha256)
#     to before the round trip;
#   * everything the install created is gone; and
#   * a file or mime default that is not ours survives.
#
# Thunderbird itself is never launched: the profile finder is a stub that names a temp dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
ok()  { pass=$((pass + 1)); printf '  ok    %s\n' "$1"; }
bad() { fail=$((fail + 1)); printf '  FAIL  %s\n' "$1"; }
check() {  # check <name> <expected> <actual>
  if [[ $2 == "$3" ]]; then ok "$1"; else bad "$1 (want [$2] got [$3])"; fi
}
check_gone()  { [[ -e $2 ]] && bad "$1 ($2 still exists)" || ok "$1"; }
check_alive() { [[ -e $2 ]] && ok "$1" || bad "$1 ($2 was removed)"; }
check_link()  { [[ -L $2 ]] && ok "$1" || bad "$1 ($2 is not a symlink)"; }

# ── the throwaway world ───────────────────────────────────────────────────────
export HOME="$TMP/home"
export XDG_CONFIG_HOME="$TMP/config"
mkdir -p "$HOME" "$XDG_CONFIG_HOME/hypr"

TB_BIN_DIR="$TMP/usr-local-bin"
POLICIES_FILE="$TMP/usr-lib/thunderbird/distribution/policies.json"
ETC_XDG_MIMEAPPS="$TMP/etc-xdg/mimeapps.list"
SYS_APPS_MIMEAPPS="$TMP/usr-share-applications/mimeapps.list"
XEMAIL_LINK="$TMP/usr-bin/x-email-client"
TB_BIN_FILE="$TMP/thunderbird-bin"
export OMARCHY_TB_BIN_DIR="$TB_BIN_DIR"
export OMARCHY_TB_POLICIES_FILE="$POLICIES_FILE"
export OMARCHY_TB_ETC_XDG_MIMEAPPS="$ETC_XDG_MIMEAPPS"
export OMARCHY_TB_SYS_MIMEAPPS="$SYS_APPS_MIMEAPPS"
export OMARCHY_TB_XEMAIL_LINK="$XEMAIL_LINK"
export OMARCHY_TB_BIN="$TB_BIN_FILE"

printf '#!/bin/bash\nexit 0\n' > "$TB_BIN_FILE"; chmod +x "$TB_BIN_FILE"
mkdir -p "$TB_BIN_DIR" "$TMP/usr-bin" "$(dirname "$POLICIES_FILE")" "$(dirname "$ETC_XDG_MIMEAPPS")" \
  "$(dirname "$SYS_APPS_MIMEAPPS")"

# A plugin tree whose heavy Python entry points are stubs — install.sh must be exercised end to
# end, but this is not a test of the XPI build or the CSS renderer. Everything else is the real
# file: policies.json, bindings.lua, set-system-default and the theme-set hook are shipped as-is.
PLUGIN="$TMP/plugin"
mkdir -p "$PLUGIN"
cp "$REPO/install.sh" "$PLUGIN/install.sh"
cp -r "$REPO/hooks" "$PLUGIN/hooks"
mkdir -p "$PLUGIN/bin"
cp "$REPO/bin/bindings.lua" "$REPO/bin/policies.json" "$REPO/bin/set-system-default" "$PLUGIN/bin/"
printf '#!/bin/bash\necho "%s/profile"\n' "$TMP" > "$PLUGIN/bin/omarchy-tb-profile"
for s in omarchy-thunderbird-apply omarchy-tb-render-css omarchy-thunderbird-rules omarchy-thunderbird-xpi; do
  printf '#!/bin/bash\nexit 0\n' > "$PLUGIN/bin/$s"
done
chmod +x "$PLUGIN/bin/"*
mkdir -p "$TMP/profile"

# ── the desktop, stubbed ──────────────────────────────────────────────────────
FAKEBIN="$TMP/fakebin"; mkdir -p "$FAKEBIN"
LOG="$TMP/desktop.log"; : > "$LOG"

cat > "$FAKEBIN/omarchy" <<STUB
#!/bin/bash
printf 'omarchy %s\n' "\$*" >> "$LOG"
case "\${1:-} \${2:-}" in
  "pkg add") exit 0 ;;
  "theme current") printf 'Catppuccin\n'; exit 0 ;;
  "hook install")
    # omarchy hook install <event> <file> -> installs under the file's basename
    dst="$XDG_CONFIG_HOME/omarchy/hooks/\${3}.d"
    mkdir -p "\$dst"; cp "\$4" "\$dst/\$(basename "\$4")"; exit 0 ;;
esac
exit 0
STUB
# sudo/pkexec run in place: every OMARCHY_TB_* target is under \$TMP, so "root" writes land in the
# throwaway tree and the real /usr, /etc are never touched.
printf '#!/bin/bash\nexec "$@"\n' > "$FAKEBIN/sudo"
printf '#!/bin/bash\nexec "$@"\n' > "$FAKEBIN/pkexec"
printf '#!/bin/bash\nexit 0\n' > "$FAKEBIN/update-desktop-database"
printf '#!/bin/bash\nexit 0\n' > "$FAKEBIN/thunderbird"

# xdg-mime / xdg-settings: a tiny model of the real mimeapps.list edit, so the install and the
# uninstall are checked against the same file format a desktop would produce.
mime_set() {  # mime_set <file> <mime> <desktop>
  local f="$1" mime="$2" desktop="$3"
  mkdir -p "$(dirname "$f")"
  [[ -f $f ]] || printf '[Default Applications]\n' > "$f"
  local tmp="$f.tmp"
  awk -v mime="$mime" -v desktop="$desktop" '
    { if ($0 == "[Default Applications]") { print; print mime "=" desktop; next }
      if ($0 ~ ("^" mime "=")) next
      print }' "$f" > "$tmp" && mv "$tmp" "$f"
}
export -f mime_set
cat > "$FAKEBIN/xdg-mime" <<STUB
#!/bin/bash
printf 'xdg-mime %s\n' "\$*" >> "$LOG"
if [[ \${1:-} == default ]]; then
  mime_set "\${XDG_CONFIG_HOME}/mimeapps.list" "\$3" "\$2"
fi
exit 0
STUB
cat > "$FAKEBIN/xdg-settings" <<STUB
#!/bin/bash
printf 'xdg-settings %s\n' "\$*" >> "$LOG"
if [[ \${1:-} == set && \${2:-} == default-url-scheme-handler ]]; then
  mime_set "\${XDG_CONFIG_HOME}/mimeapps.list" "x-scheme-handler/\$3" "\$4"
fi
exit 0
STUB
chmod +x "$FAKEBIN/"*
export PATH="$FAKEBIN:$PATH"

INSTALL="$PLUGIN/install.sh"
run() { bash "$INSTALL" "$@"; }

# ── the user's own config, with content of their own ──────────────────────────
HYPR_MAIN="$XDG_CONFIG_HOME/hypr/hyprland.lua"
AUTOSTART="$XDG_CONFIG_HOME/hypr/autostart.lua"
USER_MIMEAPPS="$XDG_CONFIG_HOME/mimeapps.list"
printf -- '-- my own hyprland.lua\nrequire("default.hypr.omarchy")\nhl.monitor({ output = "eDP-1" })\n' > "$HYPR_MAIN"
printf -- '-- my own autostart\nomarchy.launch_on_start = o.launch_on_start\n' > "$AUTOSTART"
printf '[Default Applications]\ntext/plain=org.gnome.TextEditor.desktop\n' > "$USER_MIMEAPPS"
printf '[Default Applications]\ntext/plain=org.gnome.TextEditor.desktop\n' > "$ETC_XDG_MIMEAPPS"
printf '[Default Applications]\ntext/plain=org.gnome.TextEditor.desktop\n' > "$SYS_APPS_MIMEAPPS"

sha() { sha256sum "$1" | cut -d' ' -f1; }
HYPR_BEFORE="$(sha "$HYPR_MAIN")"
AUTOSTART_BEFORE="$(sha "$AUTOSTART")"
MIME_BEFORE="$(sha "$USER_MIMEAPPS")"
ETC_BEFORE="$(sha "$ETC_XDG_MIMEAPPS")"
SYS_BEFORE="$(sha "$SYS_APPS_MIMEAPPS")"

printf 'installer contract: install then --uninstall\n'

# ── install ───────────────────────────────────────────────────────────────────
if ! out="$(run 2>&1)"; then bad "install.sh exited non-zero"; printf '%s\n' "$out" | sed 's/^/        /'; fi
check_link 'the widget backends are linked onto PATH' "$TB_BIN_DIR/omarchy-thunderbird-unread"
check_alive 'the policies.json is installed' "$POLICIES_FILE"
check_alive 'the theme-set hook is installed' "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/thunderbird-theme-set"
check_alive 'the bindings fragment is installed' "$XDG_CONFIG_HOME/hypr/thunderbird-bindings.lua"
check_alive 'the x-email-client link is made' "$XEMAIL_LINK"
check 'the require line was appended' '1' "$(grep -c 'hypr.thunderbird-bindings' "$HYPR_MAIN")"
check 'the autostart entries were appended' '2' "$(grep -c 'o.launch_on_start("' "$AUTOSTART")"
check 'the mail mimes were registered for the user' '8' "$(grep -c '=org.mozilla.Thunderbird.desktop' "$USER_MIMEAPPS")"
check 'the user config still holds their own lines' '1' "$(grep -c 'my own hyprland.lua' "$HYPR_MAIN")"

# A second install must not stack a second require block or a second autostart entry.
run >/dev/null 2>&1
check 're-installing does not add a second require line' '1' "$(grep -c 'hypr.thunderbird-bindings' "$HYPR_MAIN")"
check 're-installing does not add a second autostart entry' '1' "$(grep -c 'launch_on_start("thunderbird")' "$AUTOSTART")"

# ── uninstall ─────────────────────────────────────────────────────────────────
out="$(run --uninstall 2>&1)"; code=$?
check 'uninstalling succeeds' '0' "$code"
check_gone 'the PATH symlinks are gone' "$TB_BIN_DIR/omarchy-thunderbird-unread"
check_gone 'the policies.json is gone' "$POLICIES_FILE"
check_gone 'the theme-set hook is gone' "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/thunderbird-theme-set"
check_gone 'the bindings fragment is gone' "$XDG_CONFIG_HOME/hypr/thunderbird-bindings.lua"
check_gone 'the x-email-client link is gone' "$XEMAIL_LINK"
check 'the require line is gone' '0' "$(grep -c 'hypr.thunderbird-bindings' "$HYPR_MAIN")"
check 'no marker is left behind to stack up' '0' "$(grep -c -- '-- omarchy-thunderbird' "$HYPR_MAIN")"
check 'the autostart entries are gone' '0' "$(grep -c 'omarchy-thunderbird' "$AUTOSTART")"

# ── the round trip leaves the user's own files byte-identical ─────────────────
check 'hyprland.lua is byte-identical after an install/uninstall round trip' "$HYPR_BEFORE" "$(sha "$HYPR_MAIN")"
check 'autostart.lua is byte-identical' "$AUTOSTART_BEFORE" "$(sha "$AUTOSTART")"
check 'the user mimeapps.list is byte-identical' "$MIME_BEFORE" "$(sha "$USER_MIMEAPPS")"
check 'the /etc/xdg mimeapps.list is byte-identical' "$ETC_BEFORE" "$(sha "$ETC_XDG_MIMEAPPS")"
check 'the /usr/share mimeapps.list is byte-identical (restored from .bak)' "$SYS_BEFORE" "$(sha "$SYS_APPS_MIMEAPPS")"
check_alive 'and its .bak was kept' "${SYS_APPS_MIMEAPPS}.bak.thunderbird"
check "the user's own entries survived" 'text/plain=org.gnome.TextEditor.desktop' \
  "$(grep '^text/plain=' "$USER_MIMEAPPS")"

# ── a second round trip is still clean ────────────────────────────────────────
run >/dev/null 2>&1; run --uninstall >/dev/null 2>&1
check 'a second round trip leaves hyprland.lua byte-identical' "$HYPR_BEFORE" "$(sha "$HYPR_MAIN")"
check 'a second round trip leaves the user mimeapps.list byte-identical' "$MIME_BEFORE" "$(sha "$USER_MIMEAPPS")"

# ── a file that is not ours survives ──────────────────────────────────────────
# A policies.json that differs from the shipped one is not removed.
mkdir -p "$(dirname "$POLICIES_FILE")"; printf '{ "policies": { "SomebodyElse": true } }\n' > "$POLICIES_FILE"
# A real file (not our symlink) at a backend path is not removed.
printf '#!/bin/bash\n' > "$TB_BIN_DIR/omarchy-thunderbird-calendar"
# A bindings fragment without our first line is not removed.
printf -- '-- somebody else\nhl.bind("X", ...)\n' > "$XDG_CONFIG_HOME/hypr/thunderbird-bindings.lua"
# A theme-set hook that is not our copy is not removed.
printf 'someone else hook\n' > "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/thunderbird-theme-set"
out="$(run --uninstall 2>&1)"
check_alive 'a policies.json that is not ours survives' "$POLICIES_FILE"
check_alive 'a foreign file at a backend path survives' "$TB_BIN_DIR/omarchy-thunderbird-calendar"
check_alive 'a foreign bindings fragment survives' "$XDG_CONFIG_HOME/hypr/thunderbird-bindings.lua"
check_alive 'a foreign theme-set hook survives' "$XDG_CONFIG_HOME/omarchy/hooks/theme-set.d/thunderbird-theme-set"
check 'and every refusal is reported' '3' "$(printf '%s\n' "$out" | grep -c 'is not ours')"

# ── a mime default that is not ours is left alone ─────────────────────────────
# Install, then point mailto somewhere else, as a desktop does when the user picks a handler.
run >/dev/null 2>&1
mime_set "$USER_MIMEAPPS" x-scheme-handler/mailto org.kde.kmail2.desktop
run --uninstall >/dev/null 2>&1
check 'a mailto that the user re-pointed is left alone' 'x-scheme-handler/mailto=org.kde.kmail2.desktop' \
  "$(grep '^x-scheme-handler/mailto=' "$USER_MIMEAPPS")"
check 'but the other mail mimes we set are gone' '0' \
  "$(grep -c 'message/rfc822=org.mozilla.Thunderbird.desktop' "$USER_MIMEAPPS")"

# ── a hand-added require line does not eat its neighbour ──────────────────────
printf -- '-- my own hyprland.lua\nrequire("hypr.thunderbird-bindings")\n' > "$HYPR_MAIN"
run --uninstall >/dev/null 2>&1
check 'a hand-added require line is removed without touching the line above it' \
  '-- my own hyprland.lua' "$(cat "$HYPR_MAIN")"

printf 'installer contract: %d passed, %d failed\n' "$pass" "$fail"
(( fail == 0 ))
