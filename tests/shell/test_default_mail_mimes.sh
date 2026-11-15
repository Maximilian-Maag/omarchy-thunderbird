#!/bin/bash
# install.sh registers the *user-level* default mail MIME types; bin/set-system-default
# registers the *system-wide* ones. The two lists must agree: a type that is only in
# the system list works for apps that read the global mimeapps but silently falls back
# for the logged-in user (xdg-mime default wins for the session), and the MIME type
# this repository exists to cover — x-scheme-handler/mid (message-id links) — was
# exactly that, present in the system path and missing from the user path.
set -u

REPO="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
INSTALL="$REPO/install.sh"
SYSDEF="$REPO/bin/set-system-default"
fails=0

ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

# mimes_in <file> -> the entries of the file's MAIL_MIMES=( ... ) array, one per line,
# with quotes and surrounding whitespace stripped.
mimes_in() {
  awk '/MAIL_MIMES=\(/ { flag=1; next }
       flag && /\)/     { flag=0 }
       flag             { gsub(/["[:space:]]/, ""); if ($0 != "") print }' "$1"
}

user_mimes="$(mimes_in "$INSTALL")"
sys_mimes="$(mimes_in "$SYSDEF")"

if [[ -z "$user_mimes" || -z "$sys_mimes" ]]; then
  bad "could not parse a MAIL_MIMES array out of both files"
elif [[ $user_mimes == "$sys_mimes" ]]; then
  ok "install.sh and bin/set-system-default register the same mail MIME types"
else
  bad "the user-level and system-wide mail MIME lists differ"
  diff <(printf '%s\n' "$user_mimes") <(printf '%s\n' "$sys_mimes") | sed 's/^/       /'
fi

for mime in x-scheme-handler/mid x-scheme-handler/mailto message/rfc822; do
  if grep -qxF "$mime" <<<"$user_mimes"; then
    ok "install.sh registers $mime for the user"
  else
    bad "install.sh is missing $mime in its user-level list"
  fi
done

printf '\n'
if (( fails == 0 )); then
  echo "test_default_mail_mimes.sh: all assertions passed"
  exit 0
fi
echo "test_default_mail_mimes.sh: $fails assertion(s) failed"
exit 1
