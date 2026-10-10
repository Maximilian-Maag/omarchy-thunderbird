// user.js — Thunderbird profile preferences for omarchy-thunderbird
// Applied on first run by placing in the profile directory.
// These prefs enable userChrome.css theming and set sane defaults.

// ── Theme ─────────────────────────────────────────────────────────────────────
// Required to load userChrome.css from chrome/
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);

// Use system color scheme as the base; our userChrome.css overrides on top
user_pref("layout.css.prefers-color-scheme.content-override", 2); // system

// ── Appearance ────────────────────────────────────────────────────────────────
user_pref("mail.tabs.autoHide", false);
user_pref("mail.tabs.drawInTitlebar", true);
user_pref("browser.display.use_system_colors", false);
user_pref("browser.anchor_color", "default");
user_pref("browser.visited_color", "default");

// ── Composition ───────────────────────────────────────────────────────────────
user_pref("mail.compose.default_to_paragraph", true);
user_pref("mail.forward_message_mode", 1); // forward as attachment

// ── Privacy ───────────────────────────────────────────────────────────────────
// Block remote content in messages by default
user_pref("mail.remote_content.blocked_by_default", true);
// Don't load images in mail by default
user_pref("permissions.default.image", 2);
// Disable telemetry
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("app.normandy.enabled", false);
user_pref("app.shield.optoutstudies.enabled", false);
// Disable crash reporter
user_pref("breakpad.reportURL", "");
user_pref("browser.crashReports.unsubmittedCheck.enabled", false);

// ── UI ────────────────────────────────────────────────────────────────────────
user_pref("mail.pane_config.dynamic", 2); // wide layout (folder|thread|message)
user_pref("mailnews.default_sort_type", 18); // sort by date
user_pref("mailnews.default_sort_order", 2); // descending
user_pref("mailnews.default_view_flags", 1); // threaded
user_pref("mail.show_headers", 1); // normal headers
user_pref("mail.biff.animate_dock_icon", false);

// ── Notifications ─────────────────────────────────────────────────────────────
// Let the desktop notification daemon present new-mail alerts (Thunderbird's
// default), but keep the message preview off the alert — a notification sits on a
// shared screen, so subject-only is the private choice. Silencing Thunderbird's own
// sound avoids a second chime on top of the desktop's, and the unread count is
// worth showing in the badge.
// Each value here deliberately differs from Thunderbird's built-in default, so it
// survives into prefs.js rather than being dropped as a no-op.
user_pref("mail.biff.alert.show_preview", false);
user_pref("mail.biff.play_sound", false);
user_pref("mail.biff.use_new_count_in_badge", true);

// ── Identity / account defaults ───────────────────────────────────────────────
// No signature appended to replies (keeps long threads readable), no "you could
// encrypt this" reminder, the system GnuPG keyring allowed as an OpenPGP backend,
// and no start-page tab on launch.
user_pref("mail.identity.default.sig_on_reply", false);
user_pref("mail.openpgp.remind_encryption_possible", false);
user_pref("mail.openpgp.allow_external_gnupg", true);
user_pref("mailnews.start_page.enabled", false);

// ── Calendar/Tasks ────────────────────────────────────────────────────────────
user_pref("calendar.view.useSystemColors", false);
