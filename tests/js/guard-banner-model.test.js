// Unit tests for extension/guard-banner-model.js — the in-message banner wording.
//
// Also a mutation target (tests/mutation.json), and a cross-file contract check: every
// reason code the guard engine can emit must have banner text, or a warning would render
// with a raw code like "dkim-fail" and no explanation.
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const model = require(path.join(__dirname, '..', '..', 'extension', 'guard-banner-model.js'));
const engineSource = fs.readFileSync(path.join(__dirname, '..', '..', 'extension', 'guard-engine.js'), 'utf8');

test('an ok message produces no banner', () => {
  assert.strictEqual(model.bannerModel({ verdict: 'ok', reasons: [] }), null);
});

test('a missing or malformed verdict produces no banner', () => {
  assert.strictEqual(model.bannerModel(null), null);
  assert.strictEqual(model.bannerModel({}), null);
  assert.strictEqual(model.bannerModel({ verdict: 'unknown' }), null);
});

test('a warn verdict explains itself', () => {
  const m = model.bannerModel({ verdict: 'warn', reasons: [{ code: 'insecure-http', detail: 'no TLS' }] });
  assert.strictEqual(m.level, 'warn');
  assert.strictEqual(m.heading, 'Possible scam or phishing');
  assert.strictEqual(m.detail, 'a link is not encrypted (http) (no TLS)');
});

test('a danger verdict uses the stronger heading', () => {
  const m = model.bannerModel({ verdict: 'danger', reasons: [{ code: 'dmarc-fail' }] });
  assert.strictEqual(m.level, 'danger');
  assert.strictEqual(m.heading, 'Likely scam or phishing');
  assert.strictEqual(m.detail, 'the sender failed DMARC');
});

test('the verdict is case-insensitive', () => {
  assert.strictEqual(model.bannerModel({ verdict: 'DANGER', reasons: [] }).level, 'danger');
});

test('at most three reasons are listed', () => {
  const reasons = [
    { code: 'insecure-http' }, { code: 'shortener' }, { code: 'ip-literal-host' },
    { code: 'very-long-url' },
  ];
  const m = model.bannerModel({ verdict: 'warn', reasons });
  assert.strictEqual(m.detail.split('; ').length, 3);
  assert.ok(!m.detail.includes('unusually long'));
});

test('no reasons still yields a sensible sentence', () => {
  const m = model.bannerModel({ verdict: 'warn', reasons: [] });
  assert.strictEqual(m.detail, 'the sender or the links look suspicious');
});

test('describeReason renders the code, the detail, or neither', () => {
  assert.strictEqual(model.describeReason({ code: 'shortener' }), 'a link is hidden behind a shortener');
  assert.strictEqual(model.describeReason({ code: 'shortener', detail: 'bit.ly' }), 'a link is hidden behind a shortener (bit.ly)');
  assert.strictEqual(model.describeReason({ code: 'brand-new-code' }), 'brand new code');
  assert.strictEqual(model.describeReason({}), '');
  assert.strictEqual(model.describeReason(null), '');
});

test('every reason the engine can emit has banner wording', () => {
  const codes = new Set();
  const re = /\badd\(\s*\d+\s*,\s*"([a-z0-9-]+)"/g;
  let m;
  while ((m = re.exec(engineSource)) !== null) codes.add(m[1]);
  assert.ok(codes.size > 10, 'expected to find the engine reason codes, found ' + codes.size);
  for (const code of codes) {
    assert.ok(model.REASON_TEXT[code], 'no banner text for engine reason "' + code + '"');
  }
});
