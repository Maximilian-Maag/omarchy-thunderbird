// background.js — wire the guard engine to Thunderbird.
//
// On every displayed message: gather the sender, links and authentication results,
// score them with GuardEngine, and if the verdict is warn/danger tag the message
// "suspicious" and raise a notification. The verdict for the message on screen is
// held in memory per tab (tabVerdicts, below) so the in-message banner can ask for it.
//
// Everything is defensive: a guard that throws on an odd message is worse than no
// guard, so each step is isolated and failures are logged, not propagated.

const GUARD_TAG = "suspicious";

// Auto-sort maps the engine's boolean `star` action onto Thunderbird's built-in
// "starred" tag — the flag behind the star column in the message list.
const STAR_TAG = "starred";

// Pull http(s) links out of a message part's body text or HTML.
function extractLinks(body) {
  const found = [];
  if (!body) return found;
  if (typeof body === "string") {
    const re = /href\s*=\s*["']([^"']+)["']/gi;
    let m;
    while ((m = re.exec(body)) !== null) found.push({ href: m[1] });
    const bare = /(https?:\/\/[^\s"'<>]+)/gi;
    while ((m = bare.exec(body)) !== null) found.push({ href: m[1] });
  } else {
    // Thunderbird's MIME tree carries the decoded text/HTML on each part's `.body`
    // (a string) and that part's children under `.parts` — the top-level object has
    // the same shape. Read BOTH, or no string is ever reached and result.links is
    // always empty, leaving every link-only guard heuristic inert.
    if (typeof body.body === "string") found.push(...extractLinks(body.body));
    if (body.parts) {
      for (const part of body.parts) found.push(...extractLinks(part));
    }
  }
  return found;
}

function headerValue(headers, name) {
  const list = headers && headers[name.toLowerCase()] ? headers[name.toLowerCase()] : [];
  const first = list[0];
  return first ? String(first) : "";
}

async function scanMessage(displayed) {
  try {
    const message = await browser.messages.get(displayed.id);
    const full = await browser.messages.getFull(displayed.id);
    const headers = (full && full.headers) || {};

    const sender = {
      from: headerValue(headers, "from"),
      name: (message.author || "").replace(/\s*<[^>]*>\s*$/, ""),
      replyTo: headerValue(headers, "reply-to"),
      authResults: headerValue(headers, "authentication-results"),
    };

    const result = GuardEngine.analyze({ sender, links: extractLinks(full) });

    const payload = {
      messageId: displayed.id,
      verdict: result.verdict,
      reasons: result.sender.reasons.concat(
        result.links.reduce((acc, l) => acc.concat(l.reasons), [])),
      at: Date.now(),
    };

    if (result.verdict === "ok") return payload;

    // Tag the message so it is visible in the list even without the notification.
    try {
      const tags = (message.tags || []).slice();
      if (tags.indexOf(GUARD_TAG) === -1) {
        tags.push(GUARD_TAG);
        await browser.messages.update(displayed.id, { tags });
      }
    } catch (e) { console.warn("guard: tagging failed", e); }

    browser.notifications.create({
      type: "basic",
      title: result.verdict === "danger" ? "Scam warning" : "Suspicious message",
      message: (result.sender.reasons[0] && result.sender.reasons[0].code) ||
               "This message looks risky.",
    });

    return payload;
  } catch (e) {
    console.warn("guard: scan failed", e);
    return null;
  }
}

// ── In-message warning banner ────────────────────────────────────────────────
// The banner runs inside the message document (a separate context), so it asks here
// for the verdict of the message currently on screen. Verdicts are held per tab.
const tabVerdicts = new Map();

browser.messageDisplay.onMessageDisplayed.addListener((tab, displayed) => {
  scanMessage(displayed).then(payload => {
    if (tab) tabVerdicts.set(tab.id, payload || null);
  });
});

browser.runtime.onMessage.addListener((message, sender) => {
  if (message && message.type === "omarchy-guard-verdict") {
    const id = sender && sender.tab ? sender.tab.id : null;
    return Promise.resolve(tabVerdicts.get(id) || null);
  }
  return undefined;
});

// Inject the banner model (for the wording) and the banner script, plus its styles.
browser.messageDisplayScripts.register({
  js: [{ file: "guard-banner-model.js" }, { file: "guard-banner.js" }],
  css: [{ file: "guard-banner.css" }],
}).catch(e => console.warn("guard: banner registration failed", e));

// ── Auto-sort ────────────────────────────────────────────────────────────────
// Declarative rules (config/rules.json) decide folder + tags for arriving mail.
// The rule config is bundled into the xpi; tags come from config/tags.json so a rule
// can never reference a tag that does not exist.

async function loadConfig(name) {
  try {
    const url = browser.runtime.getURL("config/" + name);
    return await (await fetch(url)).json();
  } catch (e) {
    console.warn("sort: could not load config/" + name, e);
    return null;
  }
}

async function applySort(message) {
  const [rulesDoc, tagsDoc] = await Promise.all([loadConfig("rules.json"), loadConfig("tags.json")]);
  if (!rulesDoc || !tagsDoc) return;
  try {
    // List-Id and the attachment flag are not on the message header — they need the MIME
    // tree. Decoding the body is unnecessary, so only headers are decoded (the default).
    let full = null;
    try {
      full = await browser.messages.getFull(message.id, { decodeContent: false });
    } catch (e) {
      console.warn("sort: could not read the message for List-Id/attachments", e);
    }
    const result = SortEngine.resolveActions(
      SortEngine.messageContext(message, full), rulesDoc.rules);
    if (!result.acted) return;

    const updates = {};
    const before = message.tags || [];
    const tags = before.slice();
    (result.add_tags || []).forEach(function (tag) {
      if (tags.indexOf(tag) === -1) tags.push(tag);
    });
    // star is a boolean from the engine; the write path applies it as the "starred"
    // tag, which is what Thunderbird's star column tracks.
    if (result.star && tags.indexOf(STAR_TAG) === -1) tags.push(STAR_TAG);
    if (tags.length !== before.length) updates.tags = tags;
    // mark_read is likewise a boolean; the read flag lives directly on the message.
    if (result.mark_read) updates.read = true;
    if (Object.keys(updates).length) {
      await browser.messages.update(message.id, updates);
    }

    // Move last: resolve the configured destination against the real folder tree and
    // only move when it resolves exactly. An unresolvable name tags the message and
    // leaves it in place rather than guessing a folder.
    if (result.move_to) {
      const accounts = await browser.accounts.list();
      const destination = SortEngine.chooseFolder(
        accounts.map(a => ({ accountId: a.id, name: a.name, folders: a.folders })),
        result.move_to);
      if (destination) {
        await browser.messages.move([message.id], destination);
      } else {
        console.warn("sort: no folder named " + result.move_to + "; tagged only");
      }
    }
  } catch (e) {
    console.warn("sort: failed", e);
  }
}

browser.messages.onNewMailReceived.addListener((folder, messages) => {
  return Promise.all(messages.messages.map(applySort));
});
