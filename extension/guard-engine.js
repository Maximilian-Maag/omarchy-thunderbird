// guard-engine.js — pure heuristics that score a message for phishing / scam risk.
//
// No I/O, no browser APIs: text in, numbers out. That is what makes it testable and
// what makes it the right place for the security logic. The extension wires it to
// Thunderbird; the tests drive it directly (see tests/js/guard-engine.test.js).
//
// Every signal is a {code, detail, weight}; the weight sums to a score and the score
// maps to a verdict via rules.thresholds. The engine never claims certainty — it
// raises the score so the UI can warn.
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(typeof require === "function" ? require("./guard-rules.js") : root.GUARD_RULES);
  } else {
    root.GuardEngine = factory(root.GUARD_RULES);
  }
})(typeof self !== "undefined" ? self : this, function (RULES) {

  var DANGEROUS_SCHEMES = ["javascript", "data", "vbscript", "file"];
  var STANDARD_PORTS = ["", "80", "443"];

  function hostOf(url) {
    try {
      return new URL(url).hostname.toLowerCase();
    } catch (e) {
      return null;
    }
  }

  function schemeOf(url) {
    var match = /^([a-z][a-z0-9+.-]*):/i.exec(String(url));
    return match ? match[1].toLowerCase() : "";
  }

  // Last two labels: good enough to compare "a.example.com" with "example.com".
  function registrable(host) {
    if (!host) return "";
    var parts = String(host).replace(/\.$/, "").split(".");
    return parts.length <= 2 ? parts.join(".") : parts.slice(-2).join(".");
  }

  function domainOf(address) {
    var match = /@([^>\s]+)/.exec(String(address || ""));
    return match ? match[1].toLowerCase().replace(/[.,;]+$/, "") : "";
  }

  function isIpLiteral(host) {
    if (!host) return false;
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return true;
    return /^\[?[0-9a-f:]+\]?$/.test(host) && host.indexOf(":") !== -1;
  }

  function hasNonAscii(text) {
    return /[^\x00-\x7F]/.test(String(text || ""));
  }

  function labelCount(host) {
    return host ? host.split(".").length : 0;
  }

  function editDistance(a, b) {
    a = String(a); b = String(b);
    var prev = [];
    for (var j = 0; j <= b.length; j++) prev[j] = j;
    for (var i = 1; i <= a.length; i++) {
      var cur = [i];
      for (var k = 1; k <= b.length; k++) {
        var cost = a[i - 1] === b[k - 1] ? 0 : 1;
        cur[k] = Math.min(prev[k] + 1, cur[k - 1] + 1, prev[k - 1] + cost);
      }
      prev = cur;
    }
    return prev[b.length];
  }

  function tldOf(host) {
    var parts = String(host || "").split(".");
    return parts.length ? parts[parts.length - 1] : "";
  }

  function verdict(score, rules) {
    var t = (rules || RULES).thresholds;
    if (score >= t.danger) return "danger";
    if (score >= t.warn) return "warn";
    return "ok";
  }

  function analyzeLink(link, rules) {
    rules = rules || RULES;
    var href = String((link && link.href) || "");
    var text = String((link && link.text) || "");
    var reasons = [];
    var score = 0;

    function add(weight, code, detail) {
      score += weight;
      reasons.push({ code: code, detail: detail, weight: weight });
    }

    var scheme = schemeOf(href);
    if (DANGEROUS_SCHEMES.indexOf(scheme) !== -1) add(60, "dangerous-scheme", scheme);
    else if (scheme === "http") add(25, "insecure-http", "no TLS");

    var host = hostOf(href);
    if (host === null) {
      add(40, "unparseable-url", href.slice(0, 60));
    } else {
      if (isIpLiteral(host)) add(30, "ip-literal-host", host);
      if (/(^|\.)xn--/.test(host)) add(25, "punycode-host", host);
      if (hasNonAscii(host)) add(25, "non-ascii-host", host);
      if (rules.suspiciousTlds.indexOf(tldOf(host)) !== -1) add(15, "suspicious-tld", tldOf(host));
      if (rules.shorteners.indexOf(registrable(host)) !== -1) add(25, "shortener", host);
      if (labelCount(host) > 3) add(10, "deep-subdomain", host);
      if (href.indexOf("@") !== -1 && href.indexOf("@") < href.indexOf(host)) {
        add(30, "userinfo-trick", href.slice(0, 60));
      }
      var port = "";
      try { port = new URL(href).port; } catch (e) { port = ""; }
      if (STANDARD_PORTS.indexOf(port) === -1) add(10, "odd-port", port);

      // The classic: the visible text is one site, the link goes to another.
      var textHost = hostOf(text) || (/^[^\s/]+\.[a-z]{2,}/i.test(text) ? registrable(text.toLowerCase()) : "");
      if (textHost && host && registrable(textHost) !== registrable(host)) {
        add(30, "text-href-mismatch", text.slice(0, 40) + " -> " + host);
      }
    }

    if (href.length > 150) add(10, "very-long-url", String(href.length));

    return { score: score, verdict: verdict(score, rules), reasons: reasons };
  }

  function analyzeSender(sender, rules) {
    rules = rules || RULES;
    sender = sender || {};
    var from = String(sender.from || "");
    var name = String(sender.name || "");
    var replyTo = String(sender.replyTo || "");
    var auth = String(sender.authResults || "").toLowerCase();
    var known = sender.knownDomains || [];
    var reasons = [];
    var score = 0;

    function add(weight, code, detail) {
      score += weight;
      reasons.push({ code: code, detail: detail, weight: weight });
    }

    var fromDomain = domainOf(from);
    var replyDomain = domainOf(replyTo);
    if (!fromDomain) add(20, "malformed-from", from.slice(0, 40));

    var nameAddress = /[^\s<>@]+@([^\s<>]+)/.exec(name);
    if (nameAddress && fromDomain && nameAddress[1].toLowerCase() !== fromDomain) {
      add(35, "name-hides-address", name.slice(0, 60));
    }

    var lowerName = name.toLowerCase();
    rules.brands.forEach(function (brand) {
      if (lowerName.indexOf(brand.name) === -1) return;
      var ok = brand.domains.some(function (d) {
        return fromDomain === d || fromDomain.endsWith("." + d);
      });
      if (!ok) add(40, "brand-impersonation", brand.name + " from " + (fromDomain || "?"));
    });

    if (replyDomain && fromDomain && replyDomain !== fromDomain) {
      add(25, "reply-to-mismatch", replyDomain);
    }

    if (fromDomain) {
      if (/(^|\.)xn--/.test(fromDomain)) add(25, "punycode-sender", fromDomain);
      if (hasNonAscii(fromDomain)) add(25, "non-ascii-sender", fromDomain);
      if (rules.suspiciousTlds.indexOf(tldOf(fromDomain)) !== -1) add(15, "suspicious-sender-tld", tldOf(fromDomain));

      known.forEach(function (domain) {
        var d = registrable(String(domain).toLowerCase());
        var f = registrable(fromDomain);
        if (!d || d === f) return;
        var dist = editDistance(d, f);
        if (dist === 1 || dist === 2) add(35, "lookalike-domain", fromDomain + " ~ " + d);
      });
    }

    if (auth.indexOf("dmarc=fail") !== -1) add(40, "dmarc-fail", "authentication failed");
    if (auth.indexOf("spf=fail") !== -1) add(20, "spf-fail", "authentication failed");
    if (auth.indexOf("dkim=fail") !== -1) add(20, "dkim-fail", "authentication failed");

    return { score: score, verdict: verdict(score, rules), reasons: reasons };
  }

  function analyze(message, rules) {
    rules = rules || RULES;
    message = message || {};
    var sender = analyzeSender(message.sender || {}, rules);
    var links = (message.links || []).map(function (link) {
      return Object.assign({ href: link.href, text: link.text }, analyzeLink(link, rules));
    });

    var verdicts = [sender.verdict].concat(links.map(function (l) { return l.verdict; }));
    var overall = "ok";
    if (verdicts.indexOf("danger") !== -1) overall = "danger";
    else if (verdicts.indexOf("warn") !== -1) overall = "warn";

    return { verdict: overall, sender: sender, links: links };
  }

  return {
    hostOf: hostOf, schemeOf: schemeOf, registrable: registrable, domainOf: domainOf,
    isIpLiteral: isIpLiteral, editDistance: editDistance, tldOf: tldOf,
    verdict: verdict, analyzeLink: analyzeLink, analyzeSender: analyzeSender,
    analyze: analyze, RULES: RULES,
  };
});
