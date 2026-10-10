# Changelog

All notable changes to omarchy-thunderbird are documented here.

## [1.2.0] — 2026-10-11

### Added
- **Themes now actually apply.** The stylesheet selected a theme with an attribute
  (`:root[data-omarchy-theme="nord"]`) that only a userChromeJS loader ever sets, so on
  a stock Thunderbird every theme silently fell back to catppuccin. The theme-set hook
  now renders `chrome/userChrome.css` with the active theme inlined straight into the
  `:root` block (`bin/omarchy-tb-render-css`), so no loader is required.
- **`omarchy-thunderbird-reload`** — applies the active theme and restarts Thunderbird
  so the change is visible immediately (Thunderbird reads `userChrome.css` only at
  startup). The `theme-set` hook can auto-reload on every switch with
  `OMARCHY_THUNDERBIRD_AUTORELOAD=1`.
- **Message body theming.** `userContent.css` is rendered from the same palette, so the
  reading pane (background, links, quoted text) follows the active theme instead of the
  fixed white default.
- **Unread-mail bar widget** (`Maximilian-Maag.thunderbird`, kind `bar-widget`). It shows
  the unread count in the Omarchy bar, backed by `bin/omarchy-thunderbird-unread`, which
  counts unread messages from the profile's mbox `X-Mozilla-Status` read bit. Left-click
  opens Thunderbird.
- **Notification and identity defaults.** No message preview on new-mail alerts, no
  Thunderbird notification sound, unread count in the badge, no signature on replies, no
  OpenPGP encryption reminder, the system GnuPG keyring allowed as an OpenPGP backend, and
  the start page disabled.
- **Supplementary chrome coverage** for the compose window, address book and calendar.

### Testing
- **New `e2e` test kind** — boots real headless Thunderbird against a throwaway profile
  and asserts the profile wiring and prefs actually take effect. The harness kind was
  added to the shared tooling and re-vendored here.
- Unit, regression, integration, e2e, shell and JS coverage added for every new source,
  with all new Python/shell tools registered as mutation targets.

### Fixed
- **`userChrome.css` could be overwritten through a symlink.** If a user already had
  `chrome/userChrome.css` symlinked at the plugin's own stylesheet, rendering followed the
  symlink and wrote into the plugin source. Rendering is now atomic and replaces the
  symlink instead of writing through it.

### Internal
- Re-vendored `tools/mutator.py` and `tools/run_tests.sh` from the shared tooling
  (equivalent-mutant matching fix; `e2e` kind).

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
