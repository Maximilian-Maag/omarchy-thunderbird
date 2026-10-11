# Changelog

All notable changes to omarchy-thunderbird are documented here.

## [1.5.0] — 2026-10-11

### Added
- **Calendar backend** (`bin/omarchy-thunderbird-calendar`): upcoming events from
  Thunderbird's `calendar-data/*.sqlite`, with the timestamp unit pinned from source
  (microseconds — `USECS_PER_SECOND = 1000000` in `CalStorageItemModel`). Cancelled
  and past events are filtered; recurring events are shown as their master only.
- **Comms widget**: the bar widget now shows unread mail and the next calendar event
  (tooltip), polling both backends.
- **Chat backend** (`bin/omarchy-thunderbird-chat`): reports the chat accounts
  configured under `chat.prpls.*` in the profile. Account creation stays in
  Thunderbird's UI — credentials cannot be provisioned blindly, so this reports, it
  does not invent.
- Calendar keybinding switched to the verified `thunderbird -calendar` flag (plus a
  documented note that Chat has no CLI flag).

### Testing
- unit suites for both backends (synthetic calendar sqlite with the shipped schema;
  synthetic prefs.js); the e2e widget test now seeds a calendar store and asserts the
  calendar and chat backends against a real profile. Both CLIs are mutation targets.

## [1.4.0] — 2026-10-11

### Added
- **Auto-sort.** `config/rules.json` declares rules (from domain, subject/To
  substrings, List-Id presence, attachment) that tag and file arriving mail —
  orders, invoices, newsletters/mailing lists, code-hosting notifications. The matcher
  (`extension/sort-engine.js`) is pure and tested; the extension applies it on
  `onNewMailReceived`, unioning tags and letting the first matching destination win.
  `bin/omarchy-thunderbird-rules --validate` checks the rules before they ship, above
  all that every tag a rule applies exists in `config/tags.json`
  (otherwise the rule is a silent no-op).
- The rule and tag config is bundled into the guard `.xpi` under `config/`, so the
  extension reads the same files the repository reviews.

### Testing
- js (node:test) suite for the sort engine; unit + regression for the rules validator
  and the rule/tag cross-file contract; the xpi build test asserts the config is
  bundled. `sort-engine.js` and the rules CLI are mutation targets.

## [1.3.0] — 2026-10-11

### Added
- **Declarative config** (`config/tags.json`, `config/settings.json`) rendered into the
  profile's `user.js` by `bin/omarchy-thunderbird-apply`. Tags and preferences are now
  reviewed, diffed and tested as files, not clicked together in the UI. Merge is
  idempotent and preserves hand-added prefs.
- **Guard extension** (`extension/`, packaged by `bin/omarchy-thunderbird-xpi`): scores
  every displayed message for scam/phishing risk and, on warn/danger, tags it
  `suspicious` and raises a notification. The engine (`guard-engine.js`) is pure and
  exhaustively tested: insecure/odd schemes, IP-literal, punycode and non-ASCII hosts,
  shorteners, suspicious TLDs, deep subdomains, userinfo tricks, text-vs-href mismatch,
  and — on the sender — brand impersonation, name-hiding-address, reply-to mismatch,
  SPF/DKIM/DMARC failures and lookalike domains of known contacts.
  The extension loads because `profile/user.js` disables signature enforcement; the
  e2e suite proves a real Thunderbird loads it and marks it active.

### Fixed
- **Prefs that enterprise policy silently ignored.** `toolkit.*`, `xpinstall.*` and
  `datareporting.healthreport.*` are outside Thunderbird's policy allowlist — setting
  them via `policies.json` only logged "Preference not allowed for stability reasons".
  Those prefs now live in `user.js`, `policies.json` keeps only allowlisted prefs, and a
  unit test enforces that every policy pref is on the allowlist.

### Testing
- New e2e: the built `.xpi` is sideloaded and a real headless Thunderbird is asserted to
  load it (`extensions.json` active=true).
- Unit/regression/integration/e2e coverage for the applier, the xpi tool, the manifest,
  and the guard engine (node:test); all new sources registered as mutation targets except
  the WebExtension glue and the rules data, which are exempted with reasons.

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
