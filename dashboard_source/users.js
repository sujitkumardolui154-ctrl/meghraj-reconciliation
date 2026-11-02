
"use strict";
(() => {
  const form = document.getElementById("create-user-form");
  const button = document.getElementById("create-user");
  const label = document.getElementById("create-label");
  const status = document.getElementById("login-status");
  const password = document.getElementById("new-password");
  const confirmation = document.getElementById("confirm-password");
  let uncertain = false;

  async function requestJSON(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch(path, {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        ...options,
        signal: controller.signal
      });
      const data = await response.json();
      return {response, data};
    } finally {
      clearTimeout(timer);
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (button.disabled || uncertain || !form.reportValidity()) return;
    status.dataset.error = "false";

    if (password.value !== confirmation.value) {
      status.dataset.error = "true";
      status.textContent = "The passwords do not match.";
      confirmation.focus();
      return;
    }

    button.disabled = true;
    form.setAttribute("aria-busy", "true");
    label.textContent = "Creating…";
    status.textContent = "Preparing account creation…";
    let submitted = false;

    try {
      const csrf = await requestJSON("/auth/csrf");
      if (!csrf.response.ok || typeof csrf.data.csrf_token !== "string") {
        throw new Error("Could not prepare this request. Refresh and try again.");
      }

      submitted = true;
      const result = await requestJSON("/api/admin/users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-DIL-CSRF": csrf.data.csrf_token
        },
        body: JSON.stringify({
          display_name: document.getElementById("display-name").value.trim(),
          email: document.getElementById("new-email").value.trim(),
          password: password.value
        })
      });

      if (result.response.status === 201 && result.data.ok === true) {
        status.textContent = "Account created: " + result.data.email
          + ". Role: dashboard user. Google IAP access must be checked separately.";
        form.reset();
      } else {
        uncertain = result.response.status >= 500 || result.response.status < 400;
        let message = typeof result.data.error === "string"
          ? result.data.error : "Account creation could not be confirmed.";
        if (typeof result.data.uid === "string") {
          message += " Account ID: " + result.data.uid + ".";
        }
        if (uncertain) {
          message += " Check Identity Platform before submitting again.";
        }
        throw new Error(message);
      }
    } catch (error) {
      if (submitted && (
        error.name === "AbortError" ||
        error instanceof TypeError ||
        error instanceof SyntaxError
      )) {
        uncertain = true;
      }
      status.dataset.error = "true";
      status.textContent = uncertain
        ? "Outcome requires checking. " + (
            error.name === "AbortError" ||
            error instanceof TypeError ||
            error instanceof SyntaxError
              ? "Check Identity Platform for this email before retrying."
              : error.message
          )
        : error.name === "AbortError" || error instanceof TypeError
          ? "Connection failed before account creation. Please try again."
          : error.message;
    } finally {
      password.value = "";
      confirmation.value = "";
      form.setAttribute("aria-busy", "false");
      button.disabled = uncertain;
      label.textContent = uncertain ? "Check account status first" : "Create user";
    }
  });
})();
