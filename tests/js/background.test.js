// Unit tests for extension/background.js — the Thunderbird glue for auto-sort.
//
// background.js talks to the browser.* WebExtension APIs, which do not exist under
// node. So this test installs a mock `browser` (and `fetch`, and the GuardEngine /
// SortEngine globals the extension loads first) before requiring the file, captures
// the listeners it registers, and drives them exactly as Thunderbird would. That is
// the only way to cover the write path — the part that actually mutates a message —
// without a real Thunderbird, which the repo otherwise pins only by static checks.
//
// The bug this guards against: a rule whose actions are mark_read/star made the
// engine report acted:true, but applySort dropped both and changed nothing.
const assert = require('node:assert');
const path = require('node:path');
const test = require('node:test');

const EXT = path.join(__dirname, '..', '..', 'extension');

// The engine globals the extension's background scope shares (manifest lists
// guard-rules, guard-engine, sort-engine, then background).
global.GuardEngine = require(path.join(EXT, 'guard-engine.js'));
global.SortEngine = require(path.join(EXT, 'sort-engine.js'));

// Load background.js under a fresh mock `browser`. `opts.configs` maps a bundled
// config filename to the object its fetch() should return; `opts.message` is the
// header message handed to SortEngine. Returns the recorded API calls and the
// registered listeners, so a test can invoke them as Thunderbird would.
function loadBackground(opts = {}) {
  const calls = { update: [], move: [], storageSet: [], notifications: [] };
  const listeners = {};
  const configs = opts.configs || {};

  global.browser = {
    messages: {
      get: async (id) => opts.message || { id, tags: [], author: 'Someone <s@example.com>' },
      getFull: async () => opts.full || { headers: {} },
      update: async (id, updates) => { calls.update.push({ id, updates }); },
      move: async (ids, destination) => { calls.move.push({ ids, destination }); },
      onNewMailReceived: { addListener: (fn) => { listeners.newMail = fn; } },
    },
    accounts: { list: async () => opts.accounts || [] },
    messageDisplay: {
      onMessageDisplayed: { addListener: (fn) => { listeners.displayed = fn; } },
    },
    runtime: {
      onMessage: { addListener: (fn) => { listeners.runtimeMessage = fn; } },
      getURL: (rel) => 'https://guard.example/' + rel,
    },
    messageDisplayScripts: { register: () => Promise.resolve() },
    notifications: { create: (o) => { calls.notifications.push(o); return Promise.resolve('n'); } },
    storage: { local: { set: async (o) => { calls.storageSet.push(o); } } },
  };
  global.fetch = async (url) => {
    const name = String(url).split('/').pop();
    return { json: async () => configs[name] || { rules: [], tags: [] } };
  };

  const modulePath = path.join(EXT, 'background.js');
  delete require.cache[require.resolve(modulePath)];
  require(modulePath);
  return { calls, listeners };
}

const RULES = {
  'rules.json': { rules: [
    { name: 'read-and-star', match: { from_domain: ['bank.example'] },
      actions: { mark_read: true, star: true } },
  ] },
  'tags.json': { tags: [] },
};

const BANK = { id: 7, tags: [], author: 'Bank <no-reply@bank.example>' };

test('applySort applies mark_read as the read flag and star as the starred tag', async () => {
  const { calls, listeners } = loadBackground({ configs: RULES });
  await listeners.newMail({}, { messages: [BANK] });

  assert.strictEqual(calls.update.length, 1, 'the message must be written exactly once');
  assert.strictEqual(calls.update[0].id, BANK.id);
  assert.strictEqual(calls.update[0].updates.read, true, 'mark_read must set read:true');
  assert.ok((calls.update[0].updates.tags || []).includes('starred'),
            'star must add the "starred" tag');
});

test('a mark_read-only rule sets read without touching tags', async () => {
  const { calls, listeners } = loadBackground({
    configs: {
      'rules.json': { rules: [
        { name: 'read-only', match: { from_domain: ['bank.example'] },
          actions: { mark_read: true } },
      ] },
      'tags.json': { tags: [] },
    },
  });
  await listeners.newMail({}, { messages: [BANK] });

  assert.strictEqual(calls.update.length, 1);
  assert.strictEqual(calls.update[0].updates.read, true);
  assert.strictEqual(calls.update[0].updates.tags, undefined,
                     'no tag action means no tags write');
});

test('a non-matching message is not written', async () => {
  const { calls, listeners } = loadBackground({ configs: RULES });
  await listeners.newMail({}, { messages: [{ id: 1, tags: [], author: 'friend@example.com' }] });

  assert.deepStrictEqual(calls.update, [], 'an unmatched message must not be mutated');
});
