# Changelog

All notable changes to omarchy-thunderbird are documented here.

## [1.9.1] — 2026-10-11

### Fixed
- **The extension was missing the permissions its own features need, so tagging and
  filing silently did nothing.** `browser.messages.update` requires `messagesUpdate`
  and `browser.messages.move` requires `messagesMove` (Thunderbird's schemas/messages
  .json — the coarse `messagesModify` the manifest carried only gates script
  injection, not message mutation). Without them every `messages.update` call threw
  and was swallowed by the guard's defensive try/catch, so a suspect message was never
  tagged and an auto-sort rule never filed or tagged anything — the marquee 1.9.0
  features reported success in the tests while doing nothing in Thunderbird.

### Testing
- The manifest test now derives the required permission set from the API calls in
  `background.js` (a call→permission map) instead of listing the permissions the
  manifest already had, so a new call cannot be added without its permission.

## [1.9.0] — 2026-10-11

Closes the four gaps left after 1.8.0.

### Added
- **In-message warning banner.** The guard already tagged suspect mail and raised a
  notification, but nothing appeared in the message itself. The extension now registers
  a script and stylesheet with `messageDisplayScripts.register()`; the injected script
  asks the background for this message's verdict and renders a warn/danger banner. The
  wording lives in `guard-banner-model.js` (pure, tested, and a mutation target) and a
  cross-file test asserts every reason code the engine can emit has banner text — it
  immediately caught two drifts (`unparseable-url` misspelled, and the engine's separate
  `suspicious-sender-tld`).
- **Auto-sort actually files mail.** Previously it only tagged, and any `move_to` was
  left to Thunderbird's own filters. The engine now resolves the configured destination
  against the real folder tree (`chooseFolder`, exact name before path segment, `null`
  when nothing matches) and the background calls the verified `browser.messages.move`.
  An unresolvable destination still tags only rather than guessing a folder.
- **Push to the bar widget.** `omarchy-thunderbird-watch` watches the profile's mail
  stores (inotify, with an mtime-poll fallback) and calls the widget's own IPC handler
  (`qs ipc call Maximilian-Maag.thunderbird refresh`); the widget's timer drops to a
  five-minute safety net. Installed on PATH and added to Hyprland autostart.
- **Chat accounts as config.** `config/chat.json` (rendered by
  `omarchy-thunderbird-apply`) declares credential-free chat accounts under
  `messenger.account.<key>.*`. IRC is the usable case — it is `passwordOptional`.

### Fixed
- **All-day and floating calendar events were shown shifted by the local offset.**
  Thunderbird stores an all-day date as midnight *UTC* and a floating event as its wall
  clock "as if UTC", but the calendar backend rendered both with `fromtimestamp` — so a
  German machine showed a date-only event at 01:00/02:00 and a floating event two hours
  late. All-day dates now render as a date with no time of day and floating events keep
  their wall clock. A UTC `UNTIL`/`EXDATE` is likewise converted to local time before
  comparison, so the boundary occurrence of a series whose local time runs ahead of the
  UTC boundary is no longer dropped.
- **The chat backend looked for the wrong namespace.** It scanned
  `chat.prpls.<protocol>.<account>.<field>`, which is not where Thunderbird stores
  accounts: they live under `messenger.account.<key>.*`, read via
  `Services.prefs.getBranch("messenger.account." + key + ".")` in `imAccounts.sys.mjs`,
  with options one level deeper under `options.`. On a real profile it would have
  reported "no accounts" even when accounts existed.

### Testing
- js suites for the banner model and the folder resolver (both mutation targets); unit
  suites for the watcher and for chat-account validation/rendering. Wall-clock honesty:
  the banner's DOM injection and the move call cannot be exercised outside a real
  Thunderbird, so they are pinned by static assertions plus the e2e extension-load test,
  not by mutation.

## [1.8.0] — 2026-10-11

### Fixed
- **One cancelled occurrence of a series erased the whole recurrence.** Thunderbird
  stores recurrence *elements* one per `cal_recurrence` row — the `RRULE`, and separately
  each `EXDATE`/`RDATE` (CalStorageItemModel handles `RDATE`/`EXDATE`/`RRULE` as distinct
  item types). Reading the rows one-by-one and overwriting meant the `EXDATE` row, which
  carries no `RRULE`, wiped the rule, so an event with a single deleted occurrence
  stopped recurring and was shown as its master date alone.

  The rows are now combined per `item_id`: the `RRULE` is taken from whichever row has
  it, `EXDATE`s suppress those occurrences, and `RDATE`s add extra ones (deduplicated
  against the normal slots).

### Testing
- Unit cases for combining rows (rule survives an EXDATE row), EXDATE suppression
  keeping the series, RDATE addition, and RDATE-on-a-normal-slot deduplication.
  `bin/omarchy-thunderbird-calendar` remains the mutation target.

## [1.7.0] — 2026-10-11

### Fixed
- **A rescheduled occurrence of a recurring event showed twice.** Moving one instance
  of a series stores it as a *detached exception* — a second `cal_events` row sharing
  the master's `id` with a non-null `recurrence_id` (the original slot) and its own
  `event_start` (the new time), which is exactly how Thunderbird queries it
  (`WHERE id = :id AND cal_id = :cal_id AND recurrence_id IS NOT NULL`). The calendar
  backend now emits the exception at its new time and suppresses the master's original
  slot. It also refuses to expand an exception as its own series — `cal_recurrence` is
  keyed by the shared id, so without that guard an exception would inherit the master's
  rule and fan out.

### Testing
- Unit cases for the moved-occurrence path: the original slot is suppressed, the new
  time is used, the exception inherits no rule, and a lone exception without a resident
  master still shows. `bin/omarchy-thunderbird-calendar` remains the mutation target.

## [1.6.0] — 2026-10-11

### Fixed
- **Recurring calendar events were shown as their master occurrence only**, so a
  weekly meeting whose master is months old looked like a stale past event (and was
  filtered out entirely). The calendar backend now reads the RRULE from
  `cal_recurrence.icalString` and expands occurrences. Supported subset: FREQ
  (DAILY/WEEKLY/MONTHLY/YEARLY), INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY; a rule
  using anything else falls back to the master rather than disappearing. Also fixed:
  monthly occurrences were generated at midnight, dropping the event's time of day
  (which had excluded the master itself from its own series).

### Testing
- The recurrence expander is covered by 20+ unit cases (each FREQ, INTERVAL, BYDAY,
  BYMONTHDAY incl. months without that day, COUNT, UNTIL, unsupported freq, time-of-day
  preservation) plus a CLI-level case that seeds `cal_recurrence` and asserts expansion
  end to end. Still the `bin/omarchy-thunderbird-calendar` mutation target.

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
