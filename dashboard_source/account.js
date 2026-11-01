
"use strict";
(async () => {
  if (document.getElementById("dil-account-bar")) return;

  async function requestJSON(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, {
        credentials: "same-origin", cache: "no-store", redirect: "error",
        ...options, signal: controller.signal
      });
      return {response, data: await response.json()};
    } finally {
      clearTimeout(timer);
    }
  }

  const bar = document.createElement("div");
  bar.id = "dil-account-bar";
  bar.style.cssText = "display:flex;gap:16px;align-items:center;flex-wrap:wrap;"
    + "padding:12px 24px;background:#142139;color:#edf3ff;border-bottom:1px solid #30425f";
  const message = document.createElement("span");
  message.setAttribute("role", "status");
  message.textContent = "Checking your account…";
  bar.appendChild(message);
  document.body.prepend(bar);

  try {
    const result = await requestJSON("/auth/me");
    if (result.response.status === 401) {
      window.location.replace("/login");
      return;
    }
    if (!result.response.ok) throw new Error("Account verification unavailable.");
    message.textContent = result.data.email;

    if (result.data.administrator === true) {
      const link = document.createElement("a");
      link.href = "/users";
      link.textContent = "Create User";
      link.style.color = "#9dccff";
      bar.appendChild(link);
    }

    const logout = document.createElement("button");
    logout.type = "button";
    logout.textContent = "Sign out";
    bar.appendChild(logout);

    logout.addEventListener("click", async () => {
      logout.disabled = true;
      try {
        const csrf = await requestJSON("/auth/csrf");
        if (!csrf.response.ok || typeof csrf.data.csrf_token !== "string") {
          throw new Error("Could not prepare sign-out. Please retry.");
        }
        const ended = await requestJSON("/auth/logout", {
          method: "POST",
          headers: {"X-DIL-CSRF": csrf.data.csrf_token}
        });
        if (ended.response.ok || ended.response.status === 401) {
          window.location.replace("/login");
          return;
        }
        throw new Error(
          typeof ended.data.error === "string"
            ? ended.data.error : "Sign-out could not be confirmed."
        );
      } catch (error) {
        message.textContent = error.message + " Refresh to check your session.";
        logout.disabled = false;
      }
    });
  } catch {
    message.textContent = "Account verification unavailable. Refresh the page.";
  }
})();
