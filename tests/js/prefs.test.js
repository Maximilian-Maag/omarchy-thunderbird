// Unit tests for profile/user.js — the prefs Thunderbird applies on first run.
//
// user.js is a script of user_pref() calls, so it is evaluated in a sandbox with a
// user_pref() stub that records every pref. That exercises the shipped file itself:
// a flipped boolean or a changed number in the source fails an assertion here, which
// is also what makes profile/user.js a mutation target.
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(
  path.join(__dirname, '..', '..', 'profile', 'user.js'), 'utf8');

function loadPrefs() {
  const prefs = {};
  const sandbox = { user_pref: (key, value) => { prefs[key] = value; }, console };
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox, { filename: 'user.js' });
  return prefs;
}

test('the shipped user.js loads and sets the documented prefs', () => {
  const prefs = loadPrefs();
  assert.ok(Object.keys(prefs).length >= 20, 'user.js should set the documented prefs');
});

test('userChrome.css theming is enabled', () => {
  const prefs = loadPrefs();
  assert.strictEqual(prefs['toolkit.legacyUserProfileCustomizations.stylesheets'], true);
});

test('the appearance defaults are applied', () => {
  const prefs = loadPrefs();
  assert.strictEqual(prefs['layout.css.prefers-color-scheme.content-override'], 2);
  assert.strictEqual(prefs['mail.tabs.autoHide'], false);
  assert.strictEqual(prefs['mail.tabs.drawInTitlebar'], true);
  assert.strictEqual(prefs['browser.display.use_system_colors'], false);
});

test('the composition defaults are applied', () => {
  const prefs = loadPrefs();
  assert.strictEqual(prefs['mail.forward_message_mode'], 1);
  assert.strictEqual(prefs['mail.compose.default_to_paragraph'], true);
});

test('privacy defaults block remote content and telemetry', () => {
  const prefs = loadPrefs();
  assert.strictEqual(prefs['mail.remote_content.blocked_by_default'], true);
  assert.strictEqual(prefs['permissions.default.image'], 2);
  assert.strictEqual(prefs['datareporting.healthreport.uploadEnabled'], false);
  assert.strictEqual(prefs['toolkit.telemetry.enabled'], false);
});
