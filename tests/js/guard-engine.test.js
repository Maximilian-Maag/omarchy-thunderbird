// Unit tests for extension/guard-engine.js — the phishing/scam scoring engine.
//
// The engine is pure, so it is tested directly and exhaustively here; this is also
// what makes extension/guard-engine.js a mutation target.
const assert = require('node:assert');
const path = require('node:path');
const test = require('node:test');

const engine = require(path.join(__dirname, '..', '..', 'extension', 'guard-engine.js'));

test('url helpers', () => {
  assert.strictEqual(engine.hostOf('https://a.b.example.com/x'), 'a.b.example.com');
  assert.strictEqual(engine.hostOf('not a url'), null);
  assert.strictEqual(engine.schemeOf('javascript:alert(1)'), 'javascript');
  assert.strictEqual(engine.registrable('a.b.example.com'), 'example.com');
  assert.strictEqual(engine.registrable('example.com'), 'example.com');
  assert.strictEqual(engine.domainOf('Alice <alice@example.com>'), 'example.com');
  assert.strictEqual(engine.domainOf('nobody'), '');
  assert.strictEqual(engine.tldOf('evil.top'), 'top');
});

test('edit distance', () => {
  assert.strictEqual(engine.editDistance('example.com', 'example.com'), 0);
  assert.strictEqual(engine.editDistance('example.com', 'examp1e.com'), 1);
  assert.strictEqual(engine.editDistance('a', 'abc'), 2);
});

test('ip literal detection', () => {
  assert.strictEqual(engine.isIpLiteral('192.168.0.1'), true);
  assert.strictEqual(engine.isIpLiteral('example.com'), false);
});

test('a clean https link is ok', () => {
  const r = engine.analyzeLink({ href: 'https://example.com/news', text: 'news' });
  assert.strictEqual(r.verdict, 'ok');
  assert.deepStrictEqual(r.reasons, []);
});

test('plain http warns', () => {
  const r = engine.analyzeLink({ href: 'http://example.com/' });
  assert.strictEqual(r.verdict, 'warn');
  assert.ok(r.reasons.some(x => x.code === 'insecure-http'));
});

test('a javascript: link is danger', () => {
  const r = engine.analyzeLink({ href: 'javascript:alert(1)' });
  assert.strictEqual(r.verdict, 'danger');
  assert.ok(r.reasons.some(x => x.code === 'dangerous-scheme'));
});

test('an IP-literal host warns', () => {
  const r = engine.analyzeLink({ href: 'https://192.168.1.10/login' });
  assert.strictEqual(r.verdict, 'warn');
  assert.ok(r.reasons.some(x => x.code === 'ip-literal-host'));
});

test('punycode and non-ascii hosts warn', () => {
  assert.strictEqual(engine.analyzeLink({ href: 'https://xn--80ak6aa92e.com/' }).verdict, 'warn');
  // \u0430 is Cyrillic 'а' — a genuine homoglyph, not an ASCII 'a'.
  assert.strictEqual(engine.analyzeLink({ href: 'https://ex\u0430mple.com/' }).verdict, 'warn');
});

test('registrable keeps three labels distinct from their registrable domain', () => {
  assert.strictEqual(engine.registrable('www.example.com'), 'example.com');
  assert.strictEqual(engine.registrable('a.b.c.example.com'), 'example.com');
});

test('ip literal edge cases', () => {
  assert.strictEqual(engine.isIpLiteral(''), false);
  // hex letters without a colon are not an IPv6 literal
  assert.strictEqual(engine.isIpLiteral('abcdef'), false);
  assert.strictEqual(engine.isIpLiteral('dead:beef::1'), true);
});

test('deep subdomains are flagged only past three labels', () => {
  const three = engine.analyzeLink({ href: 'https://www.example.com/' });
  assert.ok(!three.reasons.some(x => x.code === 'deep-subdomain'));
  const four = engine.analyzeLink({ href: 'https://a.b.c.example.com/' });
  assert.ok(four.reasons.some(x => x.code === 'deep-subdomain'));
});

test('very long urls are flagged only past 150 characters', () => {
  const base = 'https://example.com/';
  const exactly150 = base + 'x'.repeat(150 - base.length);
  assert.strictEqual(exactly150.length, 150);
  assert.ok(!engine.analyzeLink({ href: exactly150 }).reasons.some(x => x.code === 'very-long-url'));
  const over = base + 'x'.repeat(151 - base.length);
  assert.ok(engine.analyzeLink({ href: over }).reasons.some(x => x.code === 'very-long-url'));
});

test('a shortener warns', () => {
  const r = engine.analyzeLink({ href: 'https://bit.ly/abc123' });
  assert.strictEqual(r.verdict, 'warn');
  assert.ok(r.reasons.some(x => x.code === 'shortener'));
});

test('text/href mismatch is caught', () => {
  const r = engine.analyzeLink({ href: 'https://paypa1.com/secure', text: 'https://paypal.com' });
  assert.ok(r.reasons.some(x => x.code === 'text-href-mismatch'));
  assert.strictEqual(r.verdict, 'warn');
});

test('userinfo trick and odd port', () => {
  const r = engine.analyzeLink({ href: 'https://example.com@evil.top/' });
  assert.ok(r.reasons.some(x => x.code === 'userinfo-trick'));
  const p = engine.analyzeLink({ href: 'https://example.com:8443/' });
  assert.ok(p.reasons.some(x => x.code === 'odd-port'));
});

test('a clean sender is ok', () => {
  const r = engine.analyzeSender({ from: 'alice@example.com', name: 'Alice' });
  assert.strictEqual(r.verdict, 'ok');
  assert.deepStrictEqual(r.reasons, []);
});

test('brand impersonation from a lookalike domain warns', () => {
  const r = engine.analyzeSender({ from: 'billing@paypal-secure.top', name: 'PayPal Service' });
  assert.ok(r.reasons.some(x => x.code === 'brand-impersonation'));
  assert.strictEqual(r.verdict, 'warn');
});

test('a display name that hides a different address is flagged', () => {
  const r = engine.analyzeSender({ from: 'bob@evil.com', name: 'support@yourbank.com' });
  assert.ok(r.reasons.some(x => x.code === 'name-hides-address'));
});

test('reply-to mismatch is flagged', () => {
  const r = engine.analyzeSender({ from: 'a@example.com', replyTo: 'b@other.net' });
  assert.ok(r.reasons.some(x => x.code === 'reply-to-mismatch'));
});

test('dmarc failure is flagged', () => {
  const r = engine.analyzeSender({ from: 'a@example.com', authResults: 'mx.google.com; dmarc=fail; spf=fail' });
  assert.ok(r.reasons.some(x => x.code === 'dmarc-fail'));
  // dmarc fail (40) + spf fail (20) crosses the danger threshold.
  assert.strictEqual(r.verdict, 'danger');
});

test('a dmarc failure alone warns', () => {
  const r = engine.analyzeSender({ from: 'a@example.com', authResults: 'dmarc=fail' });
  assert.strictEqual(r.verdict, 'warn');
});

test('passing authentication is not flagged', () => {
  const r = engine.analyzeSender({ from: 'a@example.com', authResults: 'spf=pass; dkim=pass; dmarc=pass' });
  assert.deepStrictEqual(r.reasons, []);
});

test('a lookalike of a known domain is flagged', () => {
  const r = engine.analyzeSender({ from: 'bob@examp1e.com', knownDomains: ['example.com'] });
  assert.ok(r.reasons.some(x => x.code === 'lookalike-domain'));
});

test('a non-ascii sender domain is flagged', () => {
  // A URL host is punycoded by the URL parser before we see it, but a From address
  // is not — so the non-ascii check earns its keep on the sender side.
  const r = engine.analyzeSender({ from: 'bob@ex\u0430mple.com' });
  assert.ok(r.reasons.some(x => x.code === 'non-ascii-sender'));
});

test('a punycode sender domain is flagged', () => {
  const r = engine.analyzeSender({ from: 'bob@xn--exmple-cua.com' });
  assert.ok(r.reasons.some(x => x.code === 'punycode-sender'));
});

test('a known domain itself is not flagged as lookalike', () => {
  const r = engine.analyzeSender({ from: 'bob@example.com', knownDomains: ['example.com'] });
  assert.ok(!r.reasons.some(x => x.code === 'lookalike-domain'));
});

test('verdict thresholds', () => {
  assert.strictEqual(engine.verdict(0), 'ok');
  assert.strictEqual(engine.verdict(25), 'warn');
  assert.strictEqual(engine.verdict(59), 'warn');
  assert.strictEqual(engine.verdict(60), 'danger');
});

test('analyze rolls up the worst verdict', () => {
  const clean = engine.analyze({
    sender: { from: 'a@example.com', name: 'A' },
    links: [{ href: 'https://example.com', text: 'x' }],
  });
  assert.strictEqual(clean.verdict, 'ok');

  const risky = engine.analyze({
    sender: { from: 'a@example.com', name: 'A' },
    links: [{ href: 'javascript:alert(1)' }],
  });
  assert.strictEqual(risky.verdict, 'danger');
  assert.strictEqual(risky.links.length, 1);
});
