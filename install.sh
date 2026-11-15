#!/bin/bash
# omarchy-thunderbird install script
# Run once after cloning the plugin, or re-run to update.
#
#   ./install.sh                     install / update everything
#   ./install.sh --uninstall         remove what this script installed, and only that
#
# install.sh persists changes outside the user's own config — /usr/local/bin symlinks, a
# policies.json under /usr/lib/thunderbird, the mail mimeapps entries in /etc/xdg and
# /usr/share/applications — so the removal path is the mirror of the install path, target by
# target, each one guarded so a file that is not ours is left alone. The OMARCHY_TB_* overrides
# point those system locations at a throwaway tree: an uninstall that can only be exercised as
# root is an uninstall nobody can test.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
TB_CONFIG="$CONFIG_HOME/thunderbird"

# ── what the plugin writes, in one place so install and uninstall cannot drift ──
TB_DESKTOP="org.mozilla.Thunderbird.desktop"
MAIL_MIMES=(
  x-scheme-handler/mailto
  message/rfc822
  text/calendar
  text/vcard
  text/x-vcard
  x-scheme-handler/webcal
  x-scheme-handler/webcals
  x-scheme-handler/mid
)
BACKENDS=(omarchy-thunderbird-unread omarchy-thunderbird-calendar omarchy-thunderbird-watch)

TB_BIN_DIR="${OMARCHY_TB_BIN_DIR:-/usr/local/bin}"
POLICIES_FILE="${OMARCHY_TB_POLICIES_FILE:-/usr/lib/thunderbird/distribution/policies.json}"
ETC_XDG_MIMEAPPS="${OMARCHY_TB_ETC_XDG_MIMEAPPS:-/etc/xdg/mimeapps.list}"
SYS_APPS_MIMEAPPS="${OMARCHY_TB_SYS_MIMEAPPS:-/usr/share/applications/mimeapps.list}"
XEMAIL_LINK="${OMARCHY_TB_XEMAIL_LINK:-/usr/bin/x-email-client}"

USER_MIMEAPPS="$CONFIG_HOME/mimeapps.list"
HYPR_CONFIG_DIR="$CONFIG_HOME/hypr"
HYPR_MAIN="$HYPR_CONFIG_DIR/hyprland.lua"
HYPR_FRAGMENT="$HYPR_CONFIG_DIR/thunderbird-bindings.lua"
HYPR_REQUIRE='require("hypr.thunderbird-bindings")'
HYPR_MARKER='-- omarchy-thunderbird keybindings'
AUTOSTART="$HYPR_CONFIG_DIR/autostart.lua"
THEME_SET_HOOK="$CONFIG_HOME/omarchy/hooks/theme-set.d/thunderbird-theme-set"

say() { printf '  %s\n' "$1"; }
warn() { printf 'WARNING: %s\n' "$1" >&2; }

as_root() {  # run a command that writes a root-owned location
  if (( EUID == 0 )); then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else pkexec "$@"
  fi
}

unlink_ours() {  # unlink_ours <path> <source it must point at>
  local dest="$1" source="$2"
  if [[ -L $dest ]] && [[ "$(readlink -f "$dest")" == "$(readlink -f "$source")" ]]; then
    as_root rm -f "$dest"
    say "removed $dest"
  elif [[ -e $dest ]]; then
    warn "$dest is not a link into this checkout — left alone."
  fi
}

# Remove a block that install.sh appended: the content line, the marker comment above it and
# the blank line above that — but only when the marker is actually sitting directly above the
# content line, so a hand-added line's neighbour is never eaten. Never `sed -i`: the user's
# config is only ever rewritten a line smaller.
remove_marked_block() {  # remove_marked_block <file> <marker> <content>
  local file="$1" marker="$2" content="$3"
  [[ -f $file ]] || return 0
  grep -qF -- "$content" "$file" || return 0
  local kept; kept="$(mktemp)"
  local -a lines out=()
  local line
  mapfile -t lines < "$file"
  for line in "${lines[@]}"; do
    if [[ $line == "$content" ]]; then
      if (( ${#out[@]} )) && [[ ${out[-1]} == "$marker" ]]; then
        unset 'out[-1]'
        if (( ${#out[@]} )) && [[ -z ${out[-1]} ]]; then unset 'out[-1]'; fi
      fi
      continue
    fi
    out+=("$line")
  done
  for line in ${out[@]+"${out[@]}"}; do printf '%s\n' "$line"; done > "$kept"
  mv "$kept" "$file"
}

# Drop the <mime>=<thunderbird-desktop> lines this plugin wrote from a mimeapps.list, leaving
# every other line exactly where it was. A mime whose handler is not ours any more (the user
# picked something else) is left alone. as_root=yes for the system lists.
remove_mime_lines() {  # remove_mime_lines <file> <root:yes|no>
  local file="$1" root="${2:-no}"
  [[ -f $file ]] || return 0
  local kept; kept="$(mktemp)"
  local changed=0 line key val m
  while IFS= read -r line || [[ -n $line ]]; do
    if [[ $line == *=* ]]; then
      key="${line%%=*}"; val="${line#*=}"
      for m in "${MAIL_MIMES[@]}"; do
        if [[ $key == "$m" && $val == "$TB_DESKTOP" ]]; then
          changed=1; continue 2
        fi
      done
    fi
    printf '%s\n' "$line" >> "$kept"
  done < "$file"
  if (( changed )); then
    if [[ $root == yes ]]; then as_root cp "$kept" "$file"; else cp "$kept" "$file"; fi
    say "took the mail registrations back out of $file"
  fi
  rm -f "$kept"
}

uninstall() {
  echo "omarchy-thunderbird: uninstalling from $PLUGIN_DIR"

  # 1. The widget backends on PATH.
  local backend
  for backend in "${BACKENDS[@]}"; do
    unlink_ours "$TB_BIN_DIR/$backend" "$PLUGIN_DIR/bin/$backend"
  done

  # 2. The theme-set hook (only if it is still the copy we installed).
  if [[ -f $THEME_SET_HOOK ]]; then
    if cmp -s "$PLUGIN_DIR/hooks/thunderbird-theme-set" "$THEME_SET_HOOK"; then
      rm -f "$THEME_SET_HOOK"
      say "removed the theme-set hook"
    else
      warn "$THEME_SET_HOOK is not ours — left alone."
    fi
  fi

  # 3. The system policies.json, only when it is still byte-for-byte the one we ship (JSON has
  #    no comment syntax, so identity to our source is the ownership mark).
  if [[ -f $POLICIES_FILE ]]; then
    if cmp -s "$PLUGIN_DIR/bin/policies.json" "$POLICIES_FILE"; then
      as_root rm -f "$POLICIES_FILE"
      say "removed $POLICIES_FILE"
    else
      warn "$POLICIES_FILE is not ours — left alone."
    fi
  fi

  # 4. The keybindings: the fragment, the require block, and the two autostart blocks.
  if [[ -f $HYPR_FRAGMENT ]]; then
    if head -1 "$HYPR_FRAGMENT" | grep -qF -- 'omarchy-thunderbird'; then
      rm -f "$HYPR_FRAGMENT"
      say "removed $HYPR_FRAGMENT"
    else
      warn "$HYPR_FRAGMENT is not ours — left alone."
    fi
  fi
  remove_marked_block "$HYPR_MAIN" "$HYPR_MARKER" "$HYPR_REQUIRE"
  remove_marked_block "$AUTOSTART" '-- omarchy-thunderbird: start Thunderbird at login (opens on workspace 4)' \
    'o.launch_on_start("thunderbird")'
  remove_marked_block "$AUTOSTART" '-- omarchy-thunderbird: push mail changes to the bar widget' \
    'o.launch_on_start("omarchy-thunderbird-watch")'

  # 5. The mail registrations, user then system. The user list is edited in place; the two
  #    system lists are root-owned, and /usr/share/applications keeps a .bak.thunderbird that
  #    is restored when it is there (and kept — it is the user's only copy of the original).
  remove_mime_lines "$USER_MIMEAPPS" no
  if [[ -f "${SYS_APPS_MIMEAPPS}.bak.thunderbird" ]]; then
    as_root cp "${SYS_APPS_MIMEAPPS}.bak.thunderbird" "$SYS_APPS_MIMEAPPS"
    say "restored $SYS_APPS_MIMEAPPS from its .bak (kept)"
  else
    remove_mime_lines "$SYS_APPS_MIMEAPPS" yes
  fi
  remove_mime_lines "$ETC_XDG_MIMEAPPS" yes

  # 6. The x-email-client symlink, only when it still points at Thunderbird.
  if [[ -L $XEMAIL_LINK ]] && [[ "$(readlink "$XEMAIL_LINK")" == *thunderbird* ]]; then
    as_root rm -f "$XEMAIL_LINK"
    say "removed $XEMAIL_LINK"
  elif [[ -e $XEMAIL_LINK ]]; then
    warn "$XEMAIL_LINK is not ours — left alone."
  fi

  echo ""
  echo "Done. Reload Hyprland config:  hyprctl reload"
}

if [[ ${1:-} == --uninstall ]]; then
  uninstall
  exit 0
fi

echo "omarchy-thunderbird: installing from $PLUGIN_DIR"

# ── 1. Install Thunderbird ────────────────────────────────────────────────────
omarchy pkg add thunderbird
echo "  Thunderbird installed."

# ── 2. Find (or create) the default profile ───────────────────────────────────
PROFILE="$("$PLUGIN_DIR/bin/omarchy-tb-profile" 2>/dev/null)" || PROFILE=""

if [[ -z "$PROFILE" ]]; then
  echo "  No Thunderbird profile found — creating one..."
  # Run TB briefly to create a default profile
  timeout 8 thunderbird --headless 2>/dev/null || true
  PROFILE="$("$PLUGIN_DIR/bin/omarchy-tb-profile" 2>/dev/null)" || PROFILE=""
fi

if [[ -z "$PROFILE" ]]; then
  echo "  WARNING: could not locate or create a TB profile."
  echo "  Run thunderbird once to create a profile, then re-run install.sh."
else
  echo "  Using profile: $PROFILE"
fi

# ── 3. Apply declarative prefs + tags (config/settings.json, config/tags.json) ─
if [[ -n "$PROFILE" ]]; then
  apply_log="$("$PLUGIN_DIR/bin/omarchy-thunderbird-apply" --profile "$PROFILE" 2>&1)"
  printf '%s\n' "$apply_log"
  if printf '%s' "$apply_log" | grep -q "chat accounts NOT applied"; then
    # apply skips the chat accounts while Thunderbird is open: it rewrites prefs.js on
    # exit, so an account registered now would be discarded. Say exactly what to do.
    echo ""
    echo "  NOTE: user.js and tags were applied, but the chat accounts in config/chat.json"
    echo "  were NOT — Thunderbird is running. Close it, then run:"
    echo "      $PLUGIN_DIR/bin/omarchy-thunderbird-apply --profile \"$PROFILE\""
    echo ""
  else
    echo "  Applied user.js preferences, tags and chat accounts."
  fi
fi

# ── 4. Set up userChrome.css theming ──────────────────────────────────────────
if [[ -n "$PROFILE" ]]; then
  CHROME_DIR="$PROFILE/chrome"
  mkdir -p "$CHROME_DIR"

  # Render the applied stylesheet for the current theme: the active theme is inlined
  # into the :root block, so theming works with no userChromeJS loader.
  CURRENT_THEME=$(omarchy theme current 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr ' ' '-' || true)
  [[ -z "$CURRENT_THEME" ]] && CURRENT_THEME="catppuccin"
  echo "$CURRENT_THEME" > "$CHROME_DIR/omarchy-active-theme"
  "$PLUGIN_DIR/bin/omarchy-tb-render-css" "$CURRENT_THEME" --output "$CHROME_DIR/userChrome.css"
  "$PLUGIN_DIR/bin/omarchy-tb-render-css" "$CURRENT_THEME" --kind content --output "$CHROME_DIR/userContent.css"
  echo "  Rendered userChrome.css + userContent.css for theme: $CURRENT_THEME"

  # Write the initial set-theme.uc.js (for users who run a userChromeJS loader).
  cat > "$CHROME_DIR/set-theme.uc.js" << UCJS
// Auto-generated by omarchy-thunderbird
(function() {
  const theme = "${CURRENT_THEME}";
  document.documentElement.setAttribute("data-omarchy-theme", theme);
})();
UCJS
fi

# ── 4b. Install the widget backends on PATH (unread + calendar + watcher) ─────
for backend in "${BACKENDS[@]}"; do
  BIN_SRC="$PLUGIN_DIR/bin/$backend"
  BIN_DEST="$TB_BIN_DIR/$backend"
  if [[ -L "$BIN_DEST" ]] && [[ "$(readlink -f "$BIN_DEST")" == "$(readlink -f "$BIN_SRC")" ]]; then
    echo "  $backend already on PATH."
  else
    as_root ln -sf "$BIN_SRC" "$BIN_DEST" && echo "  Installed $backend to $BIN_DEST."
  fi
done

# ── 4c. Build and install the guard extension (unsigned, loads from the profile) ─
if [[ -n "$PROFILE" ]]; then
  "$PLUGIN_DIR/bin/omarchy-thunderbird-rules" --validate
  "$PLUGIN_DIR/bin/omarchy-thunderbird-xpi" --install --profile "$PROFILE" \
    --out "$PLUGIN_DIR/build/omarchy-thunderbird-guard.xpi" >/dev/null
  echo "  Installed guard extension (scam/link warnings + auto-sort)."
fi

# ── 5. Install policies.json for system-wide managed preferences ──────────────
as_root mkdir -p "$(dirname "$POLICIES_FILE")"
as_root cp "$PLUGIN_DIR/bin/policies.json" "$POLICIES_FILE"
echo "  Installed $POLICIES_FILE."

# ── 6. Install theme-set hook ─────────────────────────────────────────────────
chmod +x "$PLUGIN_DIR/hooks/thunderbird-theme-set"
omarchy hook install theme-set "$PLUGIN_DIR/hooks/thunderbird-theme-set"
echo "  Installed theme-set hook (as thunderbird-theme-set)."

# ── 7. Wire OS keybindings into Hyprland ──────────────────────────────────────
if [[ ! -f "$HYPR_MAIN" ]]; then
  echo "  WARNING: $HYPR_MAIN not found — skipping keybinding wiring."
  echo "  Add to your hyprland.lua manually: $HYPR_REQUIRE"
else
  # Copy bindings.lua to ~/.config/hypr/thunderbird-bindings.lua so it's on Lua path
  cp "$PLUGIN_DIR/bin/bindings.lua" "$HYPR_FRAGMENT"
  if ! grep -q "thunderbird-bindings" "$HYPR_MAIN"; then
    printf '\n%s\n%s\n' "$HYPR_MARKER" "$HYPR_REQUIRE" >> "$HYPR_MAIN"
    echo "  Wired keybindings into $HYPR_MAIN"
  else
    echo "  Keybindings already wired (updated)."
  fi
fi

# ── 7b. Add Thunderbird to Hyprland autostart ─────────────────────────────────
if [[ -f "$AUTOSTART" ]] && ! grep -q "thunderbird" "$AUTOSTART"; then
  printf '\n-- omarchy-thunderbird: start Thunderbird at login (opens on workspace 4)\no.launch_on_start("thunderbird")\n' >> "$AUTOSTART"
  echo "  Added Thunderbird to autostart."
elif grep -q "thunderbird" "${AUTOSTART:-/dev/null}" 2>/dev/null; then
  echo "  Thunderbird already in autostart."
else
  echo "  No autostart.lua found — add manually: o.launch_on_start(\"thunderbird\")"
fi

# Push mail changes to the bar widget instead of polling it.
if [[ -f "$AUTOSTART" ]] && ! grep -q "omarchy-thunderbird-watch" "$AUTOSTART"; then
  printf '\n-- omarchy-thunderbird: push mail changes to the bar widget\no.launch_on_start("omarchy-thunderbird-watch")\n' >> "$AUTOSTART"
  echo "  Added the mail watcher to autostart."
fi

# ── 8. Set as default mail client ─────────────────────────────────────────────
# User-level
xdg-settings set default-url-scheme-handler mailto "$TB_DESKTOP" 2>/dev/null || true
for mime in "${MAIL_MIMES[@]}"; do
  xdg-mime default "$TB_DESKTOP" "$mime"
done
echo "  Registered MIME types for user."

# System-wide
chmod +x "$PLUGIN_DIR/bin/set-system-default"
echo "  Setting system-wide default mail client (requires sudo)..."
as_root bash "$PLUGIN_DIR/bin/set-system-default"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "Done! Start Thunderbird with: thunderbird"
echo ""
echo "Theme switches automatically with: omarchy theme set <name>"
echo "All 22 Omarchy stock themes are supported."
