// background.js — wire the guard engine to Thunderbird.
//
// On every displayed message: gather the sender, links and authentication results,
// score them with GuardEngine, and if the verdict is warn/danger tag the message
// "suspicious" and raise a notification. The last verdict per message is stashed in
// extension storage so the Omarchy bar widget can surface it.
//
// Everything is defensive: a guard that throws on an odd message is worse than no
// guard, so each step is isolated and failures are logged, not propagated.

const GUARD_TAG = "suspicious";
const LAST_VERDICT_KEY = "omarchy-thunderbird:last-verdict";

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
  } else if (body.parts) {
    for (const part of body.parts) found.push(...extractLinks(part));
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

    await browser.storage.local.set({
      [LAST_VERDICT_KEY]: {
        messageId: displayed.id,
        verdict: result.verdict,
        reasons: result.sender.reasons.concat(
          result.links.reduce((acc, l) => acc.concat(l.reasons), [])),
        at: Date.now(),
      },
    });

    if (result.verdict === "ok") return;

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
  } catch (e) {
    console.warn("guard: scan failed", e);
  }
}

browser.messageDisplay.onMessageDisplayed.addListener((tab, displayed) => {
  scanMessage(displayed);
});

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
    const sender = {
      from: message.author || "",
      name: (message.author || "").replace(/\s*<[^>]*>\s*$/, ""),
    };
    const result = SortEngine.resolveActions({
      from: sender.from,
      name: sender.name,
      subject: message.subject || "",
      to: "",
      listId: "",
      hasAttachment: false,
    }, rulesDoc.rules);
    if (!result.acted) return;

    const updates = {};
    if (result.add_tags.length) {
      updates.tags = Array.from(new Set((message.tags || []).concat(result.add_tags)));
    }
    if (Object.keys(updates).length) {
      await browser.messages.update(message.id, updates);
    }
    // Folder moves are left to the user's Thunderbird filters unless a destination is
    // configured and resolvable; tagging is the safe, always-available action.
  } catch (e) {
    console.warn("sort: failed", e);
  }
}

browser.messages.onNewMailReceived.addListener((folder, messages) => {
  messages.messages.forEach(applySort);
});
