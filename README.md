# omarchy-thunderbird

[Thunderbird](https://www.thunderbird.net/) configured for [Omarchy](https://omarchy.org/) — all 22 stock themes with automatic switching, privacy defaults, and system-wide mailto registration.

## Features

| Feature | Details |
|---------|---------|
| **22 Omarchy themes** | Full userChrome.css coverage for every stock theme — switches automatically with `omarchy theme set` |
| **Privacy defaults** | Remote content blocked, telemetry off, crash reporter disabled |
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
4. Symlinks `userChrome.css` into the profile chrome dir
5. Installs `policies.json` into `/usr/lib/thunderbird/distribution/`
6. Installs the `theme-set` hook for automatic theme switching
7. Adds Thunderbird to Hyprland autostart (opens on workspace 4)
8. Sets Thunderbird as the default mail client (user + system levels)

## Themes

Switches automatically:

```bash
omarchy theme set nord
# → Thunderbird picks up the nord palette on next launch / CSS reload
```

All 22 stock themes supported:

catppuccin · catppuccin-latte · ethereal · everforest · flexoki-light ·
gruvbox · hackerman · kanagawa · last-horizon · lumon · lupine · matte-black ·
miasma · nord · osaka-jade · retro-82 · ristretto · rose-pine · solitude ·
tokyo-night · vantablack · white

## Structure

```
omarchy-thunderbird/
├── themes/
│   └── userChrome.css      — all 22 theme palettes via CSS custom properties
├── profile/
│   └── user.js             — profile preferences (merged on install)
├── hooks/
│   └── theme-set           — omarchy hook: updates active theme on switch
├── bin/
│   ├── policies.json       — managed preferences for /usr/lib/thunderbird/distribution/
│   └── set-system-default  — privileged script: sets system-wide MIME defaults
├── install.sh              — one-shot installer
└── manifest.json           — Omarchy plugin manifest
```

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
