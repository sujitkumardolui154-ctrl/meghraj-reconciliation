/* DIL F01 — presentation-only floating chatbot. Never interprets questions locally as real financial answers.
   Future API must enforce dashboard session, claims and per-record authorization SERVER SIDE. */
(function () {
  "use strict";
  if (window.__dilFloatingAssistantLoaded) return;
  window.__dilFloatingAssistantLoaded = true;

  function mount() {
    if (!document.body || document.getElementById("dil-assistant-root")) return;
    const style = document.createElement("style");
    style.textContent = `
      #dil-assistant-root{font-family:system-ui,-apple-system,sans-serif;position:fixed;right:16px;bottom:16px;z-index:1100;color:#eff7ff}
      #dil-assistant-root *{box-sizing:border-box}
      #dil-assistant-root button{cursor:pointer;font:inherit}
      #dil-assistant-root .dil-orb{position:relative;display:inline-grid;place-items:center;width:62px;height:62px;border-radius:44%;border:2px solid #c8f7ff;background:linear-gradient(135deg,#d6faff,#6bafff 45%,#7861d7);box-shadow:0 0 24px #50cfff80;animation:dil-float 3s ease-in-out infinite}
      #dil-assistant-root .dil-visor{display:flex;justify-content:center;align-items:center;gap:12px;width:48px;height:34px;border-radius:48%;background:#071b3e;border:1px solid #6eeeff}
      #dil-assistant-root .dil-eye{width:9px;height:12px;background:#9ffbff;border-radius:9px;box-shadow:0 0 8px #6aeeff;animation:dil-blink 5s infinite}
      #dil-assistant-root .dil-launch{display:flex;align-items:center;gap:8px;border:none;background:transparent;color:#fff;padding:2px}
      #dil-assistant-root .dil-label{background:#233c78;padding:9px 13px;border-radius:24px;border:1px solid #6588cb;font-size:12px;font-weight:700;box-shadow:0 8px 18px #0007}
      #dil-assistant-root .dil-panel{width:min(350px,calc(100vw - 32px));height:min(410px,calc(100dvh - 118px));min-height:220px;margin-bottom:10px;display:flex;flex-direction:column;border-radius:18px;background:linear-gradient(145deg,#1c2f54,#0b1831);border:1px solid #526fa5;box-shadow:0 18px 45px #0008;overflow:hidden;animation:dil-open .23s ease-out}
      #dil-assistant-root .dil-panel[hidden]{display:none}
      #dil-assistant-root .dil-header{display:flex;justify-content:space-between;align-items:center;padding:12px 13px;background:#233b65;border-bottom:1px solid #43608b}
      #dil-assistant-root .dil-header strong{font-size:13px}
      #dil-assistant-root .dil-sub{color:#acc6e4;font-size:10px;margin-top:3px}
      #dil-assistant-root .dil-close{background:#152a4c;color:#fff;border:1px solid #59749d;border-radius:8px;padding:4px 10px}
      #dil-assistant-root .dil-messages{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:9px;padding:12px}
      #dil-assistant-root .dil-message{font-size:12px;line-height:1.5;max-width:91%;padding:10px 12px;border-radius:13px;white-space:pre-wrap;overflow-wrap:anywhere;animation:dil-rise .2s ease-out}
      #dil-assistant-root .dil-message.assistant{align-self:flex-start;background:#29446c}
      #dil-assistant-root .dil-message.user{align-self:flex-end;background:#305ee0}
      #dil-assistant-root .dil-form{display:flex;gap:7px;padding:10px;border-top:1px solid #394f73}
      #dil-assistant-root .dil-question{min-width:0;flex:1;background:#0c1c36;color:#fff;border:1px solid #536b92;border-radius:10px;padding:10px;font-size:12px}
      #dil-assistant-root .dil-send{border:none;border-radius:10px;color:white;background:#336de4;padding:0 13px}
      #dil-assistant-root .dil-note{padding:0 10px 9px;color:#a5bad5;font-size:10px;text-align:center}
      #dil-assistant-root :focus-visible{outline:3px solid #97ebff;outline-offset:2px}
      @keyframes dil-float{50%{transform:translateY(-7px) rotate(3deg)}}
      @keyframes dil-blink{0%,43%,47%,100%{transform:scaleY(1)}45%{transform:scaleY(.08)}}
      @keyframes dil-open{from{opacity:0;transform:translateY(10px) scale(.95)}to{opacity:1;transform:translateY(0) scale(1)}}
      @keyframes dil-rise{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
      @media(prefers-reduced-motion:reduce){#dil-assistant-root *,#dil-assistant-root *::before{animation:none!important;transition:none!important}}
    `;
    document.head.appendChild(style);

    const root = document.createElement("aside");
    root.id = "dil-assistant-root";
    root.setAttribute("aria-label", "DIL invoice intelligence assistant");
    root.innerHTML = `
      <section class="dil-panel" id="dil-assistant-panel" aria-label="Chat with DIL" hidden>
        <header class="dil-header"><div><strong>DIL Intelligence ✦</strong><div class="dil-sub">Invoice intelligence · integration preview</div></div><button class="dil-close" type="button" aria-label="Minimize DIL">−</button></header>
        <div class="dil-messages" role="log" aria-live="polite" aria-relevant="additions text"></div>
        <form class="dil-form"><input class="dil-question" aria-label="Ask DIL an invoice question" autocomplete="off" maxlength="2000" placeholder="Ask anything about invoices…" required/><button class="dil-send" type="submit">➤</button></form>
        <div class="dil-note">Source-only preview · not connected to financial data</div>
      </section>
      <button class="dil-launch" type="button" aria-expanded="false" aria-controls="dil-assistant-panel" aria-label="Open DIL assistant">
        <span class="dil-label">Ask DIL ✦</span>
        <span class="dil-orb" aria-hidden="true"><span class="dil-visor"><i class="dil-eye"></i><i class="dil-eye"></i></span></span>
      </button>`;
    document.body.appendChild(root);

    const panel = root.querySelector(".dil-panel");
    const launcher = root.querySelector(".dil-launch");
    const close = root.querySelector(".dil-close");
    const input = root.querySelector(".dil-question");
    const form = root.querySelector(".dil-form");
    const log = root.querySelector(".dil-messages");
    let lastFocus = null;
    function appendMessage(message, who) {
      const bubble = document.createElement("div");
      bubble.className = "dil-message " + who;
      bubble.textContent = message; // NEVER innerHTML for user or model content.
      log.appendChild(bubble);
      log.scrollTop = log.scrollHeight;
    }
    function toggle(open) {
      panel.hidden = !open;
      launcher.setAttribute("aria-expanded", String(open));
      launcher.setAttribute("aria-label", open ? "Minimize DIL assistant" : "Open DIL assistant");
      if (open) {
        lastFocus = document.activeElement;
        input.focus();
      } else if (lastFocus && typeof lastFocus.focus === "function") {
        lastFocus.focus();
      } else {
        launcher.focus();
      }
    }
    appendMessage("Hello! Ask any invoice-related question. I will use authorized records only when the verified read-only query API is connected.", "assistant");
    launcher.addEventListener("click", function () { toggle(panel.hidden); });
    close.addEventListener("click", function () { toggle(false); launcher.focus(); });
    panel.addEventListener("keydown", function (event) { if (event.key === "Escape") { toggle(false); launcher.focus(); } });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const question = input.value.trim();
      if (!question) return;
      appendMessage(question, "user");
      input.value = "";
      appendMessage("Secure invoice query integration is not yet available. No financial data was accessed or modified.", "assistant");
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, {once:true});
  else mount();
})();
