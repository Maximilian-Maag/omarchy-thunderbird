#!/bin/bash
# Static assertions for bin/set-system-default.
#
# The script rewrites /etc/xdg/mimeapps.list, /usr/share/applications/mimeapps.list
# and /usr/bin/x-email-client, and must run as root — there is no sandbox it can be
# executed in as part of a test suite. It is therefore exempted from mutation, and
# the contract that matters is pinned statically instead: every mail MIME type, the
# Thunderbird desktop id, and the x-email-client link.
set -u

REPO="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
SRC="$REPO/bin/set-system-default"
fails=0

ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }
has() { # has <needle> <description>
  if grep -qF -- "$1" "$SRC"; then ok "$2"; else bad "$2 (missing: $1)"; fi
}

has 'org.mozilla.Thunderbird.desktop' "registers the Thunderbird desktop id"
has '/etc/xdg/mimeapps.list' "writes the system XDG mimeapps list"
has '/usr/share/applications/mimeapps.list' "patches the Omarchy system defaults"
has 'x-email-client' "links /usr/bin/x-email-client"

for mime in \
  'x-scheme-handler/mailto' \
  'message/rfc822' \
  'text/calendar' \
  'text/vcard' \
  'text/x-vcard' \
  'x-scheme-handler/webcal' \
  'x-scheme-handler/webcals' \
  'x-scheme-handler/mid'
do
  has "$mime" "registers MIME type $mime"
done

printf '\n'
if (( fails == 0 )); then
  echo "test_set_system_default.sh: all assertions passed"
  exit 0
fi
echo "test_set_system_default.sh: $fails assertion(s) failed"
exit 1
