-- Hyprland keybindings added by omarchy-thunderbird
-- Replaces the default Hey.com webapp bindings with native Thunderbird.
-- Sourced from hyprland.lua by install.sh.

-- Unbind Hey email bindings (if preinstalled bindings are enabled)
hl.unbind("SUPER + SHIFT + E")
hl.unbind("SUPER + SHIFT + ALT + E")
hl.unbind("SUPER + SHIFT + C")

-- Thunderbird: launch or focus
o.bind("SUPER + SHIFT + E",       "Email",         { launch = "thunderbird",          focus = "^thunderbird$" })
o.bind("SUPER + SHIFT + ALT + E", "New email",     "thunderbird -compose")
o.bind("SUPER + SHIFT + C",       "Calendar",      { launch = "thunderbird",          focus = "^thunderbird$" })
