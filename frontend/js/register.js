const API_URL = "/api";
const LOGIN_URL = "login.html";
const REDIRECT_DELAY_MS = 2500;

const form = document.getElementById("register-form");
const submitBtn = document.getElementById("submit");

const fields = {
  nombre: document.getElementById("nombre"),
  apellido: document.getElementById("apellido"),
  email: document.getElementById("email"),
  telefono: document.getElementById("telefono"),
  password: document.getElementById("password"),
  password2: document.getElementById("password2"),
};

const dialog = document.getElementById("result-dialog");
const dialogIcon = document.getElementById("dialog-icon");
const dialogTitle = document.getElementById("dialog-title");
const dialogMessage = document.getElementById("dialog-message");
const dialogClose = document.getElementById("dialog-close");

function setError(name, message) {
  document.getElementById(`${name}-error`).textContent = message;
  fields[name].setAttribute("aria-invalid", message ? "true" : "false");
}

function clearErrors() {
  Object.keys(fields).forEach((name) => setError(name, ""));
}

function validate() {
  clearErrors();
  let valid = true;
  const fail = (name, message) => { setError(name, message); valid = false; };

  const nombre = fields.nombre.value.trim();
  const apellido = fields.apellido.value.trim();
  const email = fields.email.value.trim();
  const telefono = fields.telefono.value.trim();
  const password = fields.password.value;

  if (!nombre) fail("nombre", "Ingresá tu nombre.");
  if (!apellido) fail("apellido", "Ingresá tu apellido.");

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    fail("email", "Ingresá un email válido.");
  }

  if (telefono.length > 30) fail("telefono", "Máximo 30 caracteres.");

  if (password.length < 8 || password.length > 128) {
    fail("password", "Debe tener entre 8 y 128 caracteres.");
  }

  if (fields.password2.value !== password) {
    fail("password2", "Las contraseñas no coinciden.");
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

dialogClose.addEventListener("click", () => dialog.close());

dialog.addEventListener("cancel", (event) => {
  if (dialog.classList.contains("ok")) event.preventDefault();
});

Object.keys(fields).forEach((name) => {
  fields[name].addEventListener("input", () => setError(name, ""));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validate()) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Creando cuenta...";

  const payload = {
    nombre: fields.nombre.value.trim(),
    apellido: fields.apellido.value.trim(),
    email: fields.email.value.trim(),
    password: fields.password.value,
  };
  const telefono = fields.telefono.value.trim();
  if (telefono) payload.telefono = telefono;

  try {
    const response = await fetch(`${API_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (response.status === 409) {
        setError("email", "Ese email ya está registrado.");
        showDialog(false, "Registro fallido", "Ese email ya está registrado. Probá ingresando.");
      } else if (response.status === 403) {
        showDialog(false, "Registro fallido", "El registro está deshabilitado por ahora.");
      } else if (response.status >= 500) {
        showDialog(false, "Registro fallido", "Hubo un problema en el servidor. Probá de nuevo más tarde.");
      } else {
        showDialog(false, "Registro fallido", data.error || "Revisá los datos ingresados.");
      }
      return;
    }

    showDialog(true, "Registro exitoso", "Tu cuenta fue creada. Te llevamos a ingresar.");
    setTimeout(() => { window.location.href = LOGIN_URL; }, REDIRECT_DELAY_MS);
  } catch (error) {
    showDialog(false, "Registro fallido", "No se pudo conectar con el servidor. Probá de nuevo en un momento.");
  } finally {
    if (!dialog.classList.contains("ok")) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Crear cuenta";
    }
  }
});