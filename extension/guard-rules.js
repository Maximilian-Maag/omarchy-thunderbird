// guard-rules.js — the data behind the guard heuristics.
//
// Kept separate from the engine so the lists are configuration, not code, and can be
// unit-tested directly. Loaded before guard-engine.js in the extension (background
// scripts share scope) and `require`d by the node tests.
//
// These lists are deliberately small and readable. They catch the common shapes, not
// every campaign: the engine is honest that a heuristic miss is possible, and pairs
// with Thunderbird's own spam detection rather than replacing it.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.GUARD_RULES = factory();
})(typeof self !== "undefined" ? self : this, function () {
  return {
    // URL shorteners hide the real destination until clicked.
    shorteners: [
      "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
      "rebrand.ly", "cutt.ly", "shorturl.at", "rb.gy", "tiny.cc", "s.id", "lnkd.in",
    ],
    // TLDs disproportionately used by throwaway / phishing domains.
    suspiciousTlds: [
      "zip", "mov", "top", "xyz", "click", "gq", "cf", "tk", "ml", "work",
      "support", "rest", "buzz", "loan", "quest", "cam", "surf", "bar",
    ],
    // Brand -> the domains that brand legitimately uses. A message claiming the brand
    // from any other domain is impersonation.
    brands: [
      { name: "paypal", domains: ["paypal.com", "paypal.me"] },
      { name: "amazon", domains: ["amazon.com", "amazon.de", "amazon.co.uk", "amazonaws.com"] },
      { name: "microsoft", domains: ["microsoft.com", "live.com", "outlook.com", "office.com"] },
      { name: "apple", domains: ["apple.com", "icloud.com"] },
      { name: "google", domains: ["google.com", "gmail.com", "googlemail.com"] },
      { name: "netflix", domains: ["netflix.com"] },
      { name: "dhl", domains: ["dhl.com", "dhl.de"] },
      { name: "sparkasse", domains: ["sparkasse.de"] },
      { name: "volksbank", domains: ["volksbank.de"] },
      { name: "postbank", domains: ["postbank.de"] },
      { name: "telekom", domains: ["telekom.de", "t-online.de"] },
    ],
    // Verdict thresholds applied to the summed weight.
    thresholds: { warn: 25, danger: 60 },
  };
});
