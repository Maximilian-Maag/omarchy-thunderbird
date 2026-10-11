// guard-banner-model.js — pure text for the in-message warning banner.
//
// Kept separate from the DOM code so the wording/level logic is unit-testable (and a
// mutation target) without a browser: reason codes in, human sentences out.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.GuardBannerModel = factory();
})(typeof self !== "undefined" ? self : this, function () {

  // One line per reason code the guard engine can emit.
  var REASON_TEXT = {
    "dangerous-scheme": "the link uses a dangerous scheme",
    "insecure-http": "a link is not encrypted (http)",
    "unparseable-url": "a link could not be parsed",
    "ip-literal-host": "a link points at a bare IP address",
    "punycode-host": "a link uses a look-alike (punycode) domain",
    "non-ascii-host": "a link uses look-alike characters",
    "shortener": "a link is hidden behind a shortener",
    "suspicious-tld": "a link uses a frequently abused domain ending",
    "suspicious-sender-tld": "the sender domain uses a frequently abused ending",
    "deep-subdomain": "a link buries the real domain under subdomains",
    "userinfo-trick": "a link disguises its destination with an @",
    "odd-port": "a link uses an unusual port",
    "text-href-mismatch": "the shown link text does not match where it goes",
    "very-long-url": "a link is unusually long",
    "brand-impersonation": "the sender mimics a known brand",
    "name-hides-address": "the display name hides a different address",
    "reply-to-mismatch": "replies would go to a different address",
    "lookalike-domain": "the sender domain resembles one you know",
    "non-ascii-sender": "the sender domain uses look-alike characters",
    "punycode-sender": "the sender domain is punycode-encoded",
    "malformed-from": "the From header is malformed",
    "spf-fail": "the sender failed SPF",
    "dkim-fail": "the sender failed DKIM",
    "dmarc-fail": "the sender failed DMARC",
  };

  function describeReason(reason) {
    if (!reason) return "";
    var code = String(reason.code || "");
    var text = REASON_TEXT[code];
    if (!text) {
      // Unknown code: humanise it rather than dropping the signal.
      text = code ? code.replace(/-/g, " ") : "";
    }
    if (!text) return "";
    var detail = String(reason.detail || "").trim();
    return detail ? text + " (" + detail + ")" : text;
  }

  // null when there is nothing worth showing, so the caller renders no banner at all.
  function bannerModel(verdict) {
    var level = String((verdict && verdict.verdict) || "").toLowerCase();
    if (level !== "warn" && level !== "danger") return null;
    var lines = ((verdict && verdict.reasons) || []).map(describeReason).filter(Boolean);
    return {
      level: level,
      heading: level === "danger" ? "Likely scam or phishing" : "Possible scam or phishing",
      detail: lines.length
        ? lines.slice(0, 3).join("; ")
        : "the sender or the links look suspicious",
    };
  }

  return { REASON_TEXT: REASON_TEXT, describeReason: describeReason, bannerModel: bannerModel };
});
