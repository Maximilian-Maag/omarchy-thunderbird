# omarchy-thunderbird

[Thunderbird](https://www.thunderbird.net/) configured for [Omarchy](https://omarchy.org/) — all 22 stock themes (chrome *and* message body), privacy and notification defaults, an unread-mail bar widget, and system-wide mailto registration.

## Features

| Feature | Details |
|---------|---------|
| **22 Omarchy themes** | Full chrome + message-body coverage for every stock theme. Applied by rendering the active theme into `userChrome.css`, so it works with **no userChromeJS loader** |
| **Instant reload** | `omarchy-thunderbird-reload` applies the current theme and restarts Thunderbird so the change is visible now (Thunderbird reads the stylesheet at startup) |
| **Unread bar widget** | Unread count in the Omarchy bar (`Maximilian-Maag.thunderbird`); click to open Thunderbird |
| **Guard extension** | Scores every message for scam/phishing risk; tags suspect mail `suspicious` and warns |
| **Config as code** | Tags and preferences declared in `config/`, rendered into the profile — reviewable and tested |
| **Privacy defaults** | Remote content blocked, telemetry off, crash reporter disabled |
| **Notification defaults** | No message preview on alerts, no Thunderbird chime, unread count in the badge |
| **Identity defaults** | No signature on replies, no OpenPGP reminder, system GnuPG allowed as OpenPGP backend, no start page |
| **System default** | Registers Thunderbird for mailto, message/rfc822, calendar, vCard at user, `/etc/xdg/`, and Omarchy system level |
| **Sane UI defaults** | Wide layout, threaded view, date-descending sort |
| **Policies** | `policies.json` installed to `/usr/lib/thunderbird/distribution/` for system-wide managed prefs |
| **Autostart + workspace** | Starts at login and opens on workspace 4 (silent — does not steal focus) |

## Installation

### Via `omarchy plugin add` (recommended)

```bash
omarchy plugin add https://github.com/Maximilian-Maag/omarchy-thunderbird --yes
bash ~/.config/omarchy/plugins/Maximilian-Maag.thunderbird/install.sh
```

### Manual

```bash
git clone https://github.com/Maximilian-Maag/omarchy-thunderbird \
    ~/.config/omarchy/plugins/Maximilian-Maag.thunderbird
bash ~/.config/omarchy/plugins/Maximilian-Maag.thunderbird/install.sh
```

The install script:
1. Installs Thunderbird via `omarchy pkg add`
2. Finds or creates the default profile
3. Applies `user.js` preferences (merged non-destructively)
4. Renders `userChrome.css` + `userContent.css` for the current theme
5. Installs the unread backend (`omarchy-thunderbird-unread`) onto `PATH`
6. Installs `policies.json` into `/usr/lib/thunderbird/distribution/`
7. Installs the `theme-set` hook for automatic theme switching
8. Adds Thunderbird to Hyprland autostart (opens on workspace 4)
9. Sets Thunderbird as the default mail client (user + system levels)

## Themes

Switches with `omarchy theme set` — the hook renders the stylesheet immediately, and the
change is visible on the next launch:

```bash
omarchy theme set nord
omarchy-thunderbird-reload     # apply and restart Thunderbird now
```

All 22 stock themes supported:

catppuccin · catppuccin-latte · ethereal · everforest · flexoki-light ·
gruvbox · hackerman · kanagawa · last-horizon · lumon · lupine · matte-black ·
miasma · nord · osaka-jade · retro-82 · ristretto · rose-pine · solitude ·
tokyo-night · vantablack · white

Thunderbird reads `chrome/userChrome.css` only when it starts, so a theme change lands on
the next launch. `omarchy-thunderbird-reload` restarts it for you when you want it now; set
`OMARCHY_THUNDERBIRD_AUTORELOAD=1` to have the `theme-set` hook do that on every switch.

## Unread bar widget

```bash
omarchy plugin enable Maximilian-Maag.thunderbird
```

The widget polls `omarchy-thunderbird-unread`, which counts unread messages from the
profile's mbox `X-Mozilla-Status` read bit — Thunderbird's own on-disk record, no extension
or connection required:

```bash
omarchy-thunderbird-unread            # total, e.g. 3
omarchy-thunderbird-unread --json     # per-folder breakdown
omarchy-thunderbird-unread --verbose  # human-readable table
```

Only mbox stores are counted; messages that exist solely on the server (an IMAP account
with no offline copy) or in a maildir account leave no local read-state file, so they are not
counted. For the common local / offline case the count is exact.

## Structure

```
omarchy-thunderbird/
├── themes/
│   └── userChrome.css      — all 22 theme palettes (source of truth for the renderer)
├── config/
│   ├── tags.json           — declarative tag definitions
│   └── settings.json       — declarative preference overrides
├── extension/
│   ├── manifest.json       — guard WebExtension manifest
│   ├── guard-engine.js     — pure scam/phishing scoring engine
│   ├── guard-rules.js      — shortener/TLD/brand lists and thresholds
│   └── background.js       — Thunderbird wiring (messageDisplay → engine → tag/warn)
├── profile/
│   └── user.js             — base profile preferences
├── hooks/
│   └── theme-set           — omarchy hook: renders + applies the theme on switch
├── bin/
│   ├── omarchy-tb-profile       — locate the Thunderbird profile
│   ├── omarchy-tb-render-css    — render applied userChrome.css / userContent.css
│   ├── omarchy-thunderbird-apply      — apply config/ into the profile's user.js
│   ├── omarchy-thunderbird-xpi        — build/install the guard extension
│   ├── omarchy-thunderbird-reload     — apply the theme and restart Thunderbird
│   ├── omarchy-thunderbird-unread     — unread-message count (bar widget backend)
│   ├── policies.json            — managed preferences (allowlisted prefs only)
│   └── set-system-default       — privileged script: system-wide MIME defaults
├── shell/
│   └── BarWidget.qml       — unread-mail bar widget
├── install.sh              — one-shot installer
└── manifest.json           — Omarchy plugin manifest (mail-client + bar-widget)
```

## Declarative config

Tags and preferences live in files, not in the UI, and are applied to the profile by
`omarchy-thunderbird-apply`:

```bash
bin/omarchy-thunderbird-apply --print      # show the generated user.js
bin/omarchy-thunderbird-apply              # write it into the profile
```

- `config/tags.json` — tag keys, names and colours → `mailnews.tags.<key>.{tag,color}`
- `config/settings.json` — preference overrides

The merge is idempotent and preserves any pref you added by hand. A unit test checks
every configured pref actually differs from Thunderbird's built-in default (a pref equal
to the default is dropped from `prefs.js` and does nothing).

## Guard extension

`omarchy-thunderbird-xpi --install` builds and sideloads the guard extension (into the
profile's `extensions/`, which works because `user.js` disables signature enforcement).
It scores each displayed message with a pure heuristics engine (`extension/guard-engine.js`):

- links: insecure/odd schemes, IP-literal, punycode and non-ASCII hosts, shorteners,
  suspicious TLDs, deep subdomains, userinfo tricks, shown-text vs real-href mismatch;
- sender: brand impersonation, a display name hiding a different address, Reply-To
  mismatch, SPF/DKIM/DMARC failures, and lookalike domains of your known contacts.

On `warn`/`danger` it tags the message `suspicious` and raises a notification. It is a
heuristic aid, not a guarantee — it pairs with Thunderbird's own spam detection.

## Testing

Every test kind runs locally and in CI (`bash tools/run_tests.sh`):

| Kind | What it covers |
|------|----------------|
| policy as code | `tools/policy_check.py` over the repo |
| unit | the renderer, profile finder, unread counter, prefs, CSS/policies |
| regression | the documented preference contract |
| integration | hook → profile → renderer → rendered stylesheet; unread backend → profile finder |
| **e2e** | a **real headless Thunderbird** booted against a throwaway profile |
| shell | the theme-set hook, the reload CLI (stubbed process tools), QML + manifest |
| js | `profile/user.js` evaluated in a `node:vm` sandbox |
| mutation | all plugin sources, floor 0.85 |

## License

MIT

<!-- policy-as-code -->

## Policy as code

Policies that only live in prose drift. This repository enforces its own in
`tools/policy_check.py` (dependency-free), configured by `policy.json`:

    python3 tools/policy_check.py            # every tracked file
    python3 tools/policy_check.py --changed  # only what you changed (pre-commit)
    python3 tools/policy_check.py --ci       # changed vs the base branch (CI)

`--changed` is wired into `.githooks/pre-commit` and the checks also run in
`.github/workflows/policy.yml`, so a violation fails the commit or the pull
request. After cloning, enable the hook once:

    git config core.hooksPath .githooks

Documented exceptions belong in `policy.json` under `allow`, each with a reason —
an exception you can read is a decision; a check nobody runs is decoration.
