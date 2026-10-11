// Unit tests for extension/sort-engine.js — the declarative auto-sort matcher.
const assert = require('node:assert');
const path = require('node:path');
const test = require('node:test');

const engine = require(path.join(__dirname, '..', '..', 'extension', 'sort-engine.js'));

const RULES = [
  { name: 'invoices', match: { subject_contains: ['invoice'], has_attachment: true },
    actions: { move_to: 'Invoices', add_tags: ['invoice'] } },
  { name: 'lists', match: { list_id: true },
    actions: { move_to: 'Newsletters', add_tags: ['newsletter'] } },
  { name: 'github', match: { from_domain: ['github.com'] },
    actions: { move_to: 'Code', add_tags: ['action'] } },
  { name: 'star-orders', match: { from_contains: ['shop'] }, actions: { star: true } },
];

test('domain extraction and matching', () => {
  assert.strictEqual(engine.domainOf('Shop <a@mail.shop.example>'), 'mail.shop.example');
  assert.strictEqual(engine.domainOf('nobody'), '');
  assert.strictEqual(engine.domainMatches('mail.github.com', ['github.com']), true);
  assert.strictEqual(engine.domainMatches('notgithub.com', ['github.com']), false);
});

test('a rule matches only when every present condition matches', () => {
  const invoice = { subject: 'Your INVOICE 42', hasAttachment: true };
  assert.strictEqual(engine.ruleMatches(RULES[0], invoice), true);
  // subject matches but no attachment -> no match
  assert.strictEqual(engine.ruleMatches(RULES[0], { subject: 'invoice', hasAttachment: false }), false);
});

test('subject matching is case-insensitive substring', () => {
  assert.strictEqual(engine.ruleMatches(RULES[0], { subject: 'Ein Invoice für dich', hasAttachment: true }), true);
  assert.strictEqual(engine.ruleMatches(RULES[0], { subject: 'invoice', hasAttachment: true }), true);
  // substring, not fuzzy: "invoicing" does not contain "invoice"
  assert.strictEqual(engine.ruleMatches(RULES[0], { subject: 'invoicing', hasAttachment: true }), false);
});

test('list_id requires the header', () => {
  assert.strictEqual(engine.ruleMatches(RULES[1], { listId: '<x.list.example>' }), true);
  assert.strictEqual(engine.ruleMatches(RULES[1], {}), false);
});

test('from_contains checks the display name too', () => {
  assert.strictEqual(engine.ruleMatches(RULES[3], { name: 'My Shop' }), true);
  assert.strictEqual(engine.ruleMatches(RULES[3], { from: 'news@shop.example' }), true);
});

test('a non-array condition is never satisfied', () => {
  assert.strictEqual(engine.ruleMatches({ match: { subject_contains: 'invoice' } }, { subject: 'invoice' }), false);
  assert.strictEqual(engine.ruleMatches({ match: { from_contains: 'x' } }, { name: 'x' }), false);
  assert.strictEqual(engine.ruleMatches({ match: { from_domain: 'github.com' } }, { from: 'a@github.com' }), false);
});

test('resolveActions: first matching destination wins, tags union', () => {
  const result = engine.resolveActions(
    { subject: 'invoice', hasAttachment: true, listId: '<l.example>' }, RULES);
  assert.strictEqual(result.move_to, 'Invoices');
  assert.deepStrictEqual(result.add_tags, ['invoice', 'newsletter']);
  assert.deepStrictEqual(result.matched, ['invoices', 'lists']);
  assert.strictEqual(result.acted, true);
});

test('resolveActions: github mail moves to Code, unmatched mail does nothing', () => {
  const gh = engine.resolveActions({ from: 'notifications@github.com' }, RULES);
  assert.strictEqual(gh.move_to, 'Code');
  assert.deepStrictEqual(gh.add_tags, ['action']);

  const none = engine.resolveActions({ from: 'friend@example.com', subject: 'hi' }, RULES);
  assert.strictEqual(none.acted, false);
  assert.strictEqual(none.move_to, '');
  assert.deepStrictEqual(none.add_tags, []);
});

test('resolveActions: mark_read and star flags', () => {
  const r = engine.resolveActions({ from: 'news@shop.example' }, RULES);
  assert.strictEqual(r.star, true);
  assert.strictEqual(r.mark_read, false);
});

test('has_attachment=false only matches messages without one', () => {
  const rule = { match: { has_attachment: false } };
  assert.strictEqual(engine.ruleMatches(rule, { hasAttachment: false }), true);
  assert.strictEqual(engine.ruleMatches(rule, { hasAttachment: true }), false);
});

test('an empty rule matches everything but acts on nothing', () => {
  const r = engine.resolveActions({ from: 'a@b' }, [{ name: 'catch-all', match: {}, actions: {} }]);
  assert.strictEqual(r.acted, true);
  assert.strictEqual(r.move_to, '');
  assert.deepStrictEqual(r.add_tags, []);
});

const ACCOUNTS = [
  { accountId: 'acc-1', name: 'Personal', folders: [
    { name: 'Inbox', path: '/Inbox' },
    { name: 'Archive', path: '/Archive', subFolders: [
      { name: 'Invoices', path: '/Archive/Invoices' },
    ] },
  ] },
  { accountId: 'acc-2', name: 'Work', folders: [
    { name: 'Orders', path: '/Orders' },
  ] },
];

test('flattenFolders walks nested subfolders', () => {
  const names = engine.flattenFolders(ACCOUNTS[0].folders, []).map(f => f.path);
  assert.deepStrictEqual(names, ['/Inbox', '/Archive', '/Archive/Invoices']);
});

test('chooseFolder matches a folder by name', () => {
  assert.deepStrictEqual(engine.chooseFolder(ACCOUNTS, 'Orders'),
    { accountId: 'acc-2', path: '/Orders' });
});

test('chooseFolder is case-insensitive and trims', () => {
  assert.deepStrictEqual(engine.chooseFolder(ACCOUNTS, '  orders '),
    { accountId: 'acc-2', path: '/Orders' });
});

test('chooseFolder finds a nested folder', () => {
  assert.deepStrictEqual(engine.chooseFolder(ACCOUNTS, 'Invoices'),
    { accountId: 'acc-1', path: '/Archive/Invoices' });
});

test('chooseFolder prefers an exact name over a path segment', () => {
  const accounts = [{ accountId: 'a', folders: [
    { name: 'Archive', path: '/Invoices/Archive' },   // path-segment match only
    { name: 'Invoices', path: '/Mail/Invoices' },     // exact name match
  ] }];
  assert.deepStrictEqual(engine.chooseFolder(accounts, 'Invoices'),
    { accountId: 'a', path: '/Mail/Invoices' });
});

test('chooseFolder returns null for a name that does not exist', () => {
  assert.strictEqual(engine.chooseFolder(ACCOUNTS, 'Nonexistent'), null);
});

test('chooseFolder returns null for an empty destination', () => {
  assert.strictEqual(engine.chooseFolder(ACCOUNTS, '   '), null);
  assert.strictEqual(engine.chooseFolder(ACCOUNTS, ''), null);
});

test('chooseFolder tolerates the account id field name', () => {
  assert.deepStrictEqual(engine.chooseFolder([{ id: 'raw', folders: [{ name: 'X', path: '/X' }] }], 'X'),
    { accountId: 'raw', path: '/X' });
});

// ── messageContext: To/Cc from the header, List-Id and attachments from the MIME tree ──
const HEADER = { author: 'Shop <a@mail.shop.example>', subject: 'Your order',
                 recipients: ['me@example.com'], ccList: ['other@example.com'] };

test('messageContext takes From/name/subject/To from the message header', () => {
  const ctx = engine.messageContext(HEADER, null);
  assert.strictEqual(ctx.from, 'Shop <a@mail.shop.example>');
  assert.strictEqual(ctx.name, 'Shop');
  assert.strictEqual(ctx.subject, 'Your order');
  assert.strictEqual(ctx.to, 'me@example.com, other@example.com');
});

test('messageContext reads List-Id from the MIME tree headers', () => {
  const full = { headers: { 'list-id': ['<announce.list.example>'] } };
  assert.strictEqual(engine.messageContext(HEADER, full).listId, '<announce.list.example>');
  // no MIME tree (getFull failed) -> no List-Id, and it must not throw
  assert.strictEqual(engine.messageContext(HEADER, null).listId, '');
});

test('messageContext tolerates a message with missing fields', () => {
  const ctx = engine.messageContext({}, null);
  assert.deepStrictEqual(ctx, { from: '', name: '', subject: '', to: '',
                                listId: '', hasAttachment: false });
});

test('hasAttachmentPart detects Content-Disposition: attachment', () => {
  const full = { parts: [{ headers: { 'content-disposition': ['attachment; filename="a.pdf"'] } }] };
  assert.strictEqual(engine.hasAttachmentPart(full), true);
  assert.strictEqual(engine.messageContext(HEADER, full).hasAttachment, true);
});

test('hasAttachmentPart treats a named non-inline part as an attachment', () => {
  assert.strictEqual(engine.hasAttachmentPart({ name: 'report.pdf' }), true);
  // an inline image is not an attachment
  assert.strictEqual(engine.hasAttachmentPart(
    { name: 'logo.png', headers: { 'content-disposition': ['inline'] } }), false);
});

test('hasAttachmentPart recurses into sub-parts and handles no tree', () => {
  const nested = { parts: [{ parts: [{ name: 'deep.pdf' }] }] };
  assert.strictEqual(engine.hasAttachmentPart(nested), true);
  assert.strictEqual(engine.hasAttachmentPart(null), false);
  assert.strictEqual(engine.hasAttachmentPart({ contentType: 'text/plain' }), false);
});

test('a list_id rule now fires from a real MIME tree', () => {
  const full = { headers: { 'list-id': ['<x.list.example>'] } };
  assert.strictEqual(engine.ruleMatches(RULES[1], engine.messageContext(HEADER, full)), true);
});
