// guard-banner.js — runs INSIDE the message display document.
//
// Registered via browser.messageDisplayScripts.register(), so it does not share the
// background scope: it asks the background for this message's verdict and renders the
// banner itself. guard-banner-model.js is injected first and provides the wording.
(function () {
  var ID = "omarchy-guard-banner";

  function render(model) {
    var existing = document.getElementById(ID);
    if (existing) existing.remove();
    if (!model) return;
    var box = document.createElement("div");
    box.id = ID;
    box.className = "omarchy-guard-banner omarchy-guard-" + model.level;
    box.setAttribute("role", "status");
    var heading = document.createElement("strong");
    heading.textContent = model.heading;
    var detail = document.createElement("span");
    detail.textContent = model.detail;
    box.appendChild(heading);
    box.appendChild(detail);
    if (document.body) {
      document.body.insertBefore(box, document.body.firstChild);
    }
  }

  function ask(retries) {
    if (typeof browser === "undefined" || !browser.runtime || !browser.runtime.sendMessage) return;
    Promise.resolve(browser.runtime.sendMessage({ type: "omarchy-guard-verdict" }))
      .then(function (verdict) {
        var model = verdict && window.GuardBannerModel ? window.GuardBannerModel.bannerModel(verdict) : null;
        if (model) {
          render(model);
        } else if (retries > 0) {
          // The scan may still be running when the message first paints; try once more.
          setTimeout(function () { ask(retries - 1); }, 500);
        }
      })
      .catch(function () { /* no verdict: no banner */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { ask(2); });
  } else {
    ask(2);
  }
})();
