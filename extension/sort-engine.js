// sort-engine.js — pure, declarative auto-sort rules matcher.
//
// A message goes in, a set of actions comes out. No I/O and no Thunderbird APIs, so
// it is fully testable on its own (tests/js/sort-engine.test.js) and is the plugin's
// second mutation target on the JS side.
//
// Rules are evaluated in order. Every matching rule contributes tags; the FIRST
// matching rule that specifies a destination decides the folder, so the outcome does
// not depend on how many later rules also match. Rules come from config/rules.json.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SortEngine = factory();
})(typeof self !== "undefined" ? self : this, function () {

  function domainOf(address) {
    var match = /@([^>\s]+)/.exec(String(address || ""));
    return match ? match[1].toLowerCase().replace(/[.,;]+$/, "") : "";
  }

  function domainMatches(domain, list) {
    return list.some(function (entry) {
      var e = String(entry).toLowerCase();
      return domain === e || domain.endsWith("." + e);
    });
  }

  function anyContains(haystack, needles) {
    var h = String(haystack || "").toLowerCase();
    return needles.some(function (n) { return h.indexOf(String(n).toLowerCase()) !== -1; });
  }

  function checkList(field, value, condition) {
    if (condition === undefined || condition === null) return true;
    if (!Array.isArray(condition)) return false;
    return anyContains(value, condition);
  }

  function ruleMatches(rule, message) {
    var match = rule.match || {};
    var from = String(message.from || "");
    var name = String(message.name || "");
    var domain = domainOf(from);

    if (match.from_domain) {
      if (!Array.isArray(match.from_domain) || !domain || !domainMatches(domain, match.from_domain)) return false;
    }
    if (match.from_contains) {
      if (!Array.isArray(match.from_contains)) return false;
      if (!anyContains(from, match.from_contains) && !anyContains(name, match.from_contains)) return false;
    }
    if (!checkList("subject", message.subject, match.subject_contains)) return false;
    if (!checkList("to", message.to, match.to_contains)) return false;
    if (match.list_id === true && !message.listId) return false;
    if (match.list_id === false && message.listId) return false;
    if (typeof match.has_attachment === "boolean" && Boolean(message.hasAttachment) !== match.has_attachment) {
      return false;
    }
    return true;
  }

  function resolveActions(message, rules) {
    var matched = [];
    var tags = [];
    var moveTo = "";
    var markRead = false;
    var star = false;

    (rules || []).forEach(function (rule) {
      if (!ruleMatches(rule, message)) return;
      matched.push(rule.name || "unnamed");
      var actions = rule.actions || {};
      if (!moveTo && actions.move_to) moveTo = actions.move_to;
      (actions.add_tags || []).forEach(function (tag) {
        if (tags.indexOf(tag) === -1) tags.push(tag);
      });
      if (actions.mark_read) markRead = true;
      if (actions.star) star = true;
    });

    return {
      matched: matched,
      move_to: moveTo,
      add_tags: tags,
      mark_read: markRead,
      star: star,
      acted: matched.length > 0,
    };
  }

  return { domainOf: domainOf, domainMatches: domainMatches, ruleMatches: ruleMatches, resolveActions: resolveActions };
});
