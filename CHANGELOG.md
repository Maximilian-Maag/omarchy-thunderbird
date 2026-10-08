# Changelog

All notable changes to omarchy-thunderbird are documented here.

## [1.1.0] — 2026-10-08

Feature set as of this release (earlier versions predate this changelog):

- All 22 stock Omarchy themes as full `userChrome.css` coverage, switching
  automatically with `omarchy theme set`.
- Privacy defaults: remote content blocked, telemetry off, crash reporter disabled.
- Registers Thunderbird as the system default for mailto, message/rfc822, calendar
  and vCard at user, `/etc/xdg/` and Omarchy system level.
- Sane UI defaults (wide layout, threaded view, date-descending) plus a system-wide
  `policies.json` in `/usr/lib/thunderbird/distribution/`.
- Starts at login and opens on workspace 4, silently.
