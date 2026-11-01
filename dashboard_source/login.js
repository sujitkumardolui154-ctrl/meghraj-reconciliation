
"use strict";
(() => {
  const form = document.getElementById("login-form");
  const email = document.getElementById("email");
  const password = document.getElementById("password");
  const button = document.getElementById("sign-in");
  const label = document.getElementById("button-label");
  const status = document.getElementById("login-status");
  const toggle = document.getElementById("toggle-password");

  toggle.addEventListener("click", () => {
    const show = password.type === "password";
    password.type = show ? "text" : "password";
    toggle.textContent = show ? "Hide" : "Show";
    toggle.setAttribute("aria-pressed", String(show));
  });

  async function fetchJSON(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(url, {
        cache: "no-store",
        credentials: "same-origin",
        redirect: "error",
        ...options,
        signal: controller.signal
      });
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error("Unexpected server response. Refresh and try again.");
      }
      return {response, data};
    } finally {
      clearTimeout(timer);
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (button.disabled || !form.reportValidity()) return;
    button.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.dataset.error = "false";
    status.textContent = "Signing in…";
    label.textContent = "Please wait";
    let signedIn = null;

    try {
      const config = await fetchJSON("/auth/config");
      if (!config.response.ok || typeof config.data.apiKey !== "string") {
        throw new Error("Login setup is not complete. Contact the administrator.");
      }
      const csrf = await fetchJSON("/auth/csrf");
      if (!csrf.response.ok || typeof csrf.data.csrf_token !== "string") {
        throw new Error("Could not prepare sign-in. Refresh and try again.");
      }

      signedIn = await fetchJSON(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
          + encodeURIComponent(config.data.apiKey),
        {
          method: "POST",
          credentials: "omit",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            email: email.value.trim(),
            password: password.value,
            returnSecureToken: true
          })
        }
      );
      password.value = "";

      if (!signedIn.response.ok) {
        const code = signedIn.data?.error?.message || "";
        if (code.startsWith("TOO_MANY_ATTEMPTS")) {
          throw new Error("Too many attempts. Please wait before trying again.");
        }
        throw new Error("Sign-in failed. Check your email and password, or contact the administrator.");
      }
      if (typeof signedIn.data.idToken !== "string") {
        throw new Error("Sign-in could not be completed. Please try again.");
      }

      const session = await fetchJSON("/auth/session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-DIL-CSRF": csrf.data.csrf_token
        },
        body: JSON.stringify({idToken: signedIn.data.idToken})
      });
      if (!session.response.ok || session.data.ok !== true) {
        throw new Error(
          typeof session.data.error === "string"
            ? session.data.error
            : "Could not open your dashboard session."
        );
      }

      status.textContent = "Signed in. Opening your dashboard…";
      window.location.replace("/");
    } catch (error) {
      status.dataset.error = "true";
      status.textContent = error.name === "AbortError"
        ? "The request timed out. Refresh the page before trying again."
        : error instanceof TypeError
          ? "Connection failed. Check your internet connection and try again."
          : error.message;
    } finally {
      if (signedIn?.data) {
        delete signedIn.data.idToken;
        delete signedIn.data.refreshToken;
      }
      signedIn = null;
      password.value = "";
      password.type = "password";
      toggle.textContent = "Show";
      toggle.setAttribute("aria-pressed", "false");
      button.disabled = false;
      label.textContent = "Sign in";
      form.setAttribute("aria-busy", "false");
    }
  });
})();
