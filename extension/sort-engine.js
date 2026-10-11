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

  function flattenFolders(folders, out) {
    (folders || []).forEach(function (folder) {
      if (!folder) return;
      out.push({
        name: String(folder.name || ""),
        path: String(folder.path || folder.name || ""),
      });
      flattenFolders(folder.subFolders || folder.children, out);
    });
    return out;
  }

  // Resolve a configured destination name to a concrete folder. Exact name matches win
  // over a mere path-segment match, and the first account/folder in order wins, so the
  // outcome is deterministic. Returns null when nothing matches, which the caller treats
  // as "tag only, do not move" — never guess a folder.
  function chooseFolder(accounts, destination) {
    var want = String(destination || "").trim().toLowerCase();
    if (!want) return null;
    var candidates = [];
    (accounts || []).forEach(function (account) {
      var accountId = account && account.accountId !== undefined ? account.accountId : (account || {}).id;
      flattenFolders(account && account.folders, []).forEach(function (folder) {
        candidates.push({ accountId: accountId, path: folder.path, name: folder.name.toLowerCase() });
      });
    });
    var exact = candidates.filter(function (c) { return c.name === want; })[0];
    if (exact) return { accountId: exact.accountId, path: exact.path };
    var partial = candidates.filter(function (c) {
      return c.path.toLowerCase().split("/").indexOf(want) !== -1;
    })[0];
    return partial ? { accountId: partial.accountId, path: partial.path } : null;
  }

  function headerValue(headers, name) {
    var list = headers && headers[name] ? headers[name] : [];
    var first = list[0];
    return first ? String(first) : "";
  }

  // A MIME part is an attachment when its Content-Disposition says so, or when it is a
  // named part that is not explicitly inline (a forwarded message, a PDF, an image…).
  function hasAttachmentPart(part) {
    if (!part) return false;
    var disposition = headerValue(part.headers, "content-disposition").toLowerCase();
    if (disposition.indexOf("attachment") === 0) return true;
    if (part.name && disposition.indexOf("inline") !== 0) return true;
    return (part.parts || []).some(hasAttachmentPart);
  }

  // The matcher context for a message. To/Cc come straight from the message header;
  // List-Id and the attachment flag live in the MIME tree, so pass the getFull() result
  // as the second argument. Without it, those two conditions simply see nothing.
  function messageContext(message, full) {
    var author = String((message && message.author) || "");
    var to = ((message && message.recipients) || []).concat((message && message.ccList) || []);
    return {
      from: author,
      name: author.replace(/\s*<[^>]*>\s*$/, ""),
      subject: String((message && message.subject) || ""),
      to: to.join(", "),
      listId: headerValue(full && full.headers, "list-id"),
      hasAttachment: hasAttachmentPart(full),
    };
  }

  return {
    domainOf: domainOf,
    domainMatches: domainMatches,
    ruleMatches: ruleMatches,
    resolveActions: resolveActions,
    flattenFolders: flattenFolders,
    chooseFolder: chooseFolder,
    headerValue: headerValue,
    hasAttachmentPart: hasAttachmentPart,
    messageContext: messageContext,
  };
});
