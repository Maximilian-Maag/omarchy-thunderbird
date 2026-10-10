# Changelog

All notable changes to omarchy-thunderbird are documented here.

## [1.1.1] — 2026-10-08

### Fixed
- **Two tests were skipped with a stale reason.** `tests/test_unit_mutator.py` carried the
  vendored copy of the mutator tests with their end-to-end cases `@unittest.skip`ped, and the
  reason pointed at notes from the session that wrote them — while the cause had since been
  fixed: the synthetic fixture returned `n + 1` where its own test asserted `10`, so the
  runner's baseline gate refused to score it. The fixture is corrected and both tests run
  again (the module now reports zero skips). A skip whose reason no longer applies is worse
  than no test: it hides coverage that is actually available.

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
