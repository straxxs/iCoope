const API_URL = "/api";
const LANDING_URL = "index.html"; // cambiar si la landing tiene otro nombre
const REDIRECT_DELAY_MS = 2500;

// Si ya hay sesión iniciada, no mostrar el login.
if (localStorage.getItem("icoope_token")) {
  window.location.replace(LANDING_URL);
}

const form = document.getElementById("login-form");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const emailError = document.getElementById("email-error");
const passwordError = document.getElementById("password-error");
const submitBtn = document.getElementById("submit");
const toggleBtn = document.getElementById("toggle-password");

const dialog = document.getElementById("result-dialog");
const dialogIcon = document.getElementById("dialog-icon");
const dialogTitle = document.getElementById("dialog-title");
const dialogMessage = document.getElementById("dialog-message");
const dialogClose = document.getElementById("dialog-close");

function setFieldError(input, errorEl, message) {
  errorEl.textContent = message;
  input.setAttribute("aria-invalid", message ? "true" : "false");
}

function validate() {
  const email = emailInput.value.trim();
  const password = passwordInput.value;
  let valid = true;

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    setFieldError(emailInput, emailError, "Ingresá un email válido.");
    valid = false;
  } else {
    setFieldError(emailInput, emailError, "");
  }

  if (password.length < 1 || password.length > 128) {
    setFieldError(passwordInput, passwordError, "Ingresá tu contraseña.");
    valid = false;
  } else {
    setFieldError(passwordInput, passwordError, "");
  }

  return valid;
}

function showDialog(ok, title, message) {
  dialog.classList.toggle("ok", ok);
  dialog.classList.toggle("fail", !ok);
  dialogIcon.textContent = ok ? "✓" : "✕";
  dialogTitle.textContent = title;
  dialogMessage.textContent = message;
  if (!dialog.open) dialog.showModal();
}

toggleBtn.addEventListener("click", () => {
  const show = passwordInput.type === "password";
  passwordInput.type = show ? "text" : "password";
  toggleBtn.textContent = show ? "Ocultar" : "Mostrar";
  toggleBtn.setAttribute("aria-pressed", String(show));
  toggleBtn.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
});

dialogClose.addEventListener("click", () => dialog.close());

// En el popup de éxito no se puede cerrar con Esc: la redirección sigue igual.
dialog.addEventListener("cancel", (event) => {
  if (dialog.classList.contains("ok")) event.preventDefault();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validate()) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Ingresando...";

  try {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: emailInput.value.trim(),
        password: passwordInput.value,
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (response.status === 401) {
        // No se aclara si falló el email o la contraseña (mejor para la seguridad).
        setFieldError(emailInput, emailError, "");
        setFieldError(passwordInput, passwordError, "Revisá tu email y contraseña.");
        emailInput.setAttribute("aria-invalid", "true");
        showDialog(false, "Login fallido", "Email o contraseña incorrectos.");
      } else if (response.status >= 500) {
        showDialog(false, "Login fallido", "Hubo un problema en el servidor. Probá de nuevo más tarde.");
      } else {
        showDialog(false, "Login fallido", data.error || "No se pudo iniciar sesión.");
      }
      return;
    }

    localStorage.setItem("icoope_token", data.access_token);
    localStorage.setItem("icoope_user", JSON.stringify(data.usuario));

    showDialog(true, "Login exitoso", "Te estamos llevando a la página principal.");
    setTimeout(() => { window.location.href = LANDING_URL; }, REDIRECT_DELAY_MS);
  } catch (error) {
    showDialog(false, "Login fallido", "No se pudo conectar con el servidor. Probá de nuevo en un momento.");
  } finally {
    // En éxito el botón queda bloqueado hasta la redirección.
    if (!dialog.classList.contains("ok")) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Ingresar";
    }
  }
});

// Limpia el error de un campo apenas la persona vuelve a escribir.
emailInput.addEventListener("input", () => setFieldError(emailInput, emailError, ""));
passwordInput.addEventListener("input", () => {
  setFieldError(passwordInput, passwordError, "");
  setFieldError(emailInput, emailError, "");
});