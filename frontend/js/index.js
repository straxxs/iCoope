const API = "/api";
const TOKEN_KEY = "icoope_token";
const USER_KEY = "icoope_user";
const CART_KEY = "icoope_cart";
const LOGIN_URL = "login.html";

const PUBLISHERS = ["ADMIN", "COOPERADORA", "DOCENTE", "STAFF"];
const MODERATORS = ["ADMIN", "COOPERADORA"];
const MANAGERS = ["ADMIN", "COOPERADORA", "STAFF"];

const ESTADOS = {
  PENDING: "Pendiente de pago",
  APPROVED: "Pagado",
  REJECTED: "Rechazado",
  CANCELLED: "Cancelado",
  READY: "Listo para retirar",
  DELIVERED: "Entregado",
};

/* ---------- Utilidades ---------- */
const $ = (selector, root = document) => root.querySelector(selector);

const money = (value) =>
  new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS" }).format(Number(value));

const fdate = (value) =>
  new Date(value).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" });

// Crea elementos sin innerHTML, así el contenido de los usuarios nunca se interpreta como HTML.
function h(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) if (kid != null) node.append(kid);
  return node;
}

let toastTimer;
function toast(message, fail = false) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.toggle("fail", fail);
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, 4000);
}

/* ---------- Sesión ---------- */
let user = null;
try { user = JSON.parse(localStorage.getItem(USER_KEY)); } catch { user = null; }

const token = () => localStorage.getItem(TOKEN_KEY);
const hasRole = (roles) => !!user && roles.some((role) => user.roles.includes(role));

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  user = null;
  window.location.href = LOGIN_URL;
}

async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (token()) headers.Authorization = `Bearer ${token()}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(API + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("No se pudo conectar con el servidor.");
  }

  const data = await response.json().catch(() => ({}));

  if (response.status === 401 && token()) {
    logout();
    throw new Error("Tu sesión expiró. Ingresá de nuevo.");
  }
  if (!response.ok) throw new Error(data.error || "Ocurrió un error inesperado.");
  return data;
}

async function run(action) {
  try { return await action(); }
  catch (error) { toast(error.message, true); }
}

function renderAuth() {
  const box = $("#auth");
  box.replaceChildren();

  if (user) {
    box.append(
      h("span", {}, `Hola, ${user.nombre}`),
      h("button", { class: "btn ghost small", type: "button", onclick: logout }, "Salir"),
    );
  } else {
    box.append(
      h("a", { href: LOGIN_URL }, "Ingresar"),
      h("a", { href: "register.html" }, "Registrate"),
    );
  }

  $("#new-post").hidden = !hasRole(PUBLISHERS);
}

/* ---------- Navegación ---------- */
const VIEWS = {
  novedades: loadNovedades,
  tienda: loadTienda,
  calendario: loadCalendario,
  cuenta: loadCuenta,
  transparencia: () => {},
};

function route() {
  const name = location.hash.slice(1);
  const view = name in VIEWS ? name : "novedades";

  document.querySelectorAll(".view").forEach((node) => {
    node.hidden = node.id !== `view-${view}`;
  });
  document.querySelectorAll(".nav a").forEach((link) => {
    if (link.dataset.view === view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });

  run(VIEWS[view]);
}

/* ---------- Novedades ---------- */
const postState = { page: 1, perPage: 10 };

async function loadNovedades() {
  const params = new URLSearchParams({ page: postState.page, per_page: postState.perPage });
  if ($("#only-urgent").checked) params.set("urgente", "true");

  const [data] = await Promise.all([api(`/posts?${params}`), loadSideEvents()]);
  const list = $("#posts");
  list.replaceChildren();

  if (!data.publicaciones.length) {
    list.append(h("p", { class: "empty" }, "Todavía no hay novedades publicadas."));
  }

  for (const post of data.publicaciones) list.append(postCard(post));

  const pages = Math.max(1, Math.ceil(data.total / data.per_page));
  const pager = $("#posts-pager");
  pager.replaceChildren();

  if (pages > 1) {
    pager.append(
      h("button", {
        class: "btn ghost small", type: "button", disabled: data.page <= 1,
        onclick: () => { postState.page -= 1; run(loadNovedades); },
      }, "Anterior"),
      h("span", {}, `Página ${data.page} de ${pages}`),
      h("button", {
        class: "btn ghost small", type: "button", disabled: data.page >= pages,
        onclick: () => { postState.page += 1; run(loadNovedades); },
      }, "Siguiente"),
    );
  }
}

function postCard(post) {
  const canHide = user && (post.id_autor === user.id_usuario || hasRole(MODERATORS));
  const card = h("article", { class: `post${post.urgente ? " urgent" : ""}` },
    post.urgente ? h("span", { class: "tag urgent" }, "Urgente") : null,
    h("h2", {}, post.titulo),
    h("time", { datetime: post.fecha_publicacion }, fdate(post.fecha_publicacion)),
    h("p", {}, post.contenido),
  );

  if (canHide) {
    card.append(h("div", { class: "actions" },
      h("button", {
        class: "btn danger small", type: "button",
        onclick: () => run(async () => {
          if (!confirm("¿Ocultar esta publicación?")) return;
          await api(`/posts/${post.id_publicacion}`, { method: "DELETE" });
          toast("Publicación ocultada.");
          await loadNovedades();
        }),
      }, "Ocultar"),
    ));
  }
  return card;
}

let eventsCache = null;

async function getEvents() {
  if (!eventsCache) eventsCache = (await api("/events?per_page=100")).eventos;
  return eventsCache;
}

async function loadSideEvents() {
  const list = $("#side-events");
  const now = new Date();
  const events = (await getEvents()).filter((e) => new Date(e.fecha_fin) >= now).slice(0, 5);

  list.replaceChildren();
  if (!events.length) list.append(h("li", { class: "muted" }, "No hay eventos próximos."));

  for (const e of events) {
    list.append(h("li", {},
      h("strong", {}, e.titulo),
      h("small", {}, `${fdate(e.fecha_inicio)} - ${e.espacio}`),
    ));
  }
}

/* Publicar */
const postDialog = $("#post-dialog");

$("#new-post").addEventListener("click", () => {
  $("#post-form").reset();
  $("#p-error").textContent = "";
  postDialog.showModal();
});
$("#p-cancel").addEventListener("click", () => postDialog.close());
$("#only-urgent").addEventListener("change", () => { postState.page = 1; run(loadNovedades); });

$("#post-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const titulo = $("#p-titulo").value.trim();
  const contenido = $("#p-contenido").value.trim();
  const error = $("#p-error");

  if (!titulo || !contenido) {
    error.textContent = "Completá el título y el contenido.";
    return;
  }

  const button = $("#p-submit");
  button.disabled = true;
  try {
    await api("/posts", {
      method: "POST",
      body: { titulo, contenido, urgente: $("#p-urgente").checked },
    });
    postDialog.close();
    toast("Publicación creada.");
    postState.page = 1;
    await loadNovedades();
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
  }
});

/* ---------- Tienda ---------- */
const shop = { page: 1, categoriesLoaded: false };
let cart = [];
try { cart = JSON.parse(localStorage.getItem(CART_KEY)) || []; } catch { cart = []; }

const saveCart = () => localStorage.setItem(CART_KEY, JSON.stringify(cart));

async function loadTienda() {
  if (!shop.categoriesLoaded) {
    const { categorias } = await api("/categories");
    const select = $("#f-cat");
    for (const c of categorias) select.append(h("option", { value: c.id_categoria }, c.nombre));
    shop.categoriesLoaded = true;
  }

  const params = new URLSearchParams({ page: shop.page, per_page: 12 });
  if ($("#f-q").value.trim()) params.set("q", $("#f-q").value.trim());
  if ($("#f-cat").value) params.set("id_categoria", $("#f-cat").value);
  if ($("#f-tipo").value) params.set("es_evento", $("#f-tipo").value);

  const data = await api(`/products?${params}`);
  const grid = $("#products");
  grid.replaceChildren();

  if (!data.productos.length) grid.append(h("p", { class: "empty" }, "No encontramos productos con esos filtros."));
  for (const product of data.productos) grid.append(productCard(product));

  const pages = Math.max(1, Math.ceil(data.total / data.per_page));
  const pager = $("#products-pager");
  pager.replaceChildren();

  if (pages > 1) {
    pager.append(
      h("button", {
        class: "btn ghost small", type: "button", disabled: data.page <= 1,
        onclick: () => { shop.page -= 1; run(loadTienda); },
      }, "Anterior"),
      h("span", {}, `Página ${data.page} de ${pages}`),
      h("button", {
        class: "btn ghost small", type: "button", disabled: data.page >= pages,
        onclick: () => { shop.page += 1; run(loadTienda); },
      }, "Siguiente"),
    );
  }

  renderCart();
}

function productCard(p) {
  const stock = p.stock_total;
  const stockText = stock === 0
    ? "Agotado"
    : p.es_evento
      ? `Quedan ${stock} lugares`
      : `Stock: ${stock}`;

  return h("article", { class: "product" },
    h("div", {},
      p.es_evento ? h("span", { class: "tag urgent" }, "Evento") : h("span", { class: "tag" }, p.categoria),
    ),
    h("h3", {}, p.nombre),
    p.es_evento && p.fecha_evento ? h("small", { class: "muted" }, fdate(p.fecha_evento)) : null,
    h("span", { class: "grow" }),
    h("span", { class: "price" }, money(p.precio)),
    h("span", { class: stock > 0 && stock <= 5 ? "low" : "muted" }, stockText),
    h("button", {
      class: "btn", type: "button", disabled: stock === 0,
      onclick: () => run(() => openProduct(p.id_producto)),
    }, "Ver opciones"),
  );
}

/* Diálogo de producto */
const productDialog = $("#product-dialog");
let currentProduct = null;

async function openProduct(id) {
  const { producto } = await api(`/products/${id}`);
  currentProduct = producto;

  $("#pd-title").textContent = producto.nombre;
  $("#pd-desc").textContent = producto.descripcion || "";
  $("#pd-meta").textContent = `${money(producto.precio)}${
    producto.es_evento && producto.fecha_evento ? ` - ${fdate(producto.fecha_evento)}` : ""
  }`;
  $("#pd-error").textContent = "";
  $("#pd-qty").value = 1;

  const select = $("#pd-variant");
  select.replaceChildren();

  for (const v of producto.variantes) {
    select.append(h("option", { value: v.id_variante, disabled: v.stock === 0 },
      `${v.nombre} (${v.stock > 0 ? `${v.stock} disponibles` : "agotado"})`));
  }

  if (!producto.variantes.some((v) => v.stock > 0)) {
    $("#pd-error").textContent = "No hay stock disponible.";
  }

  productDialog.showModal();
}

$("#pd-cancel").addEventListener("click", () => productDialog.close());

$("#pd-add").addEventListener("click", () => {
  const variant = currentProduct.variantes.find((v) => String(v.id_variante) === $("#pd-variant").value);
  const qty = Number($("#pd-qty").value);
  const error = $("#pd-error");

  if (!variant || variant.stock === 0) { error.textContent = "Elegí una opción con stock."; return; }
  if (!Number.isInteger(qty) || qty < 1) { error.textContent = "La cantidad debe ser al menos 1."; return; }

  const line = cart.find((l) => l.id_variante === variant.id_variante);
  const total = (line ? line.cantidad : 0) + qty;

  if (total > variant.stock) { error.textContent = `Solo quedan ${variant.stock} disponibles.`; return; }

  if (line) line.cantidad = total;
  else {
    cart.push({
      id_variante: variant.id_variante,
      producto: currentProduct.nombre,
      variante: variant.nombre,
      precio: currentProduct.precio,
      stock: variant.stock,
      cantidad: qty,
    });
  }

  saveCart();
  renderCart();
  productDialog.close();
  toast("Agregado al carrito.");
});

/* Carrito */
function renderCart() {
  const box = $("#cart");
  box.replaceChildren();

  if (!cart.length) {
    box.append(h("p", { class: "muted" }, "Tu carrito está vacío. Elegí un producto para empezar."));
    return;
  }

  let total = 0;

  for (const line of cart) {
    total += Number(line.precio) * line.cantidad;

    const change = (delta) => {
      line.cantidad += delta;
      if (line.cantidad < 1) cart = cart.filter((l) => l !== line);
      else if (line.cantidad > line.stock) line.cantidad = line.stock;
      saveCart();
      renderCart();
    };

    box.append(h("div", { class: "cart-line" },
      h("div", {}, h("strong", {}, line.producto), h("br"), h("small", { class: "muted" }, line.variante)),
      h("strong", {}, money(Number(line.precio) * line.cantidad)),
      h("div", { class: "qty" },
        h("button", { class: "btn ghost small", type: "button", "aria-label": "Quitar uno", onclick: () => change(-1) }, "-"),
        h("span", {}, String(line.cantidad)),
        h("button", { class: "btn ghost small", type: "button", "aria-label": "Agregar uno", onclick: () => change(1) }, "+"),
      ),
    ));
  }

  box.append(
    h("div", { class: "cart-total" }, h("span", {}, "Total"), h("span", {}, money(total))),
    h("button", { class: "btn full", type: "button", id: "checkout", onclick: checkout }, "Proceder al pago"),
    h("p", { class: "muted" }, "Reservamos tu stock durante 15 minutos mientras pagás."),
  );
}

async function checkout() {
  if (!user) { window.location.href = LOGIN_URL; return; }

  const button = $("#checkout");
  button.disabled = true;

  await run(async () => {
    await api("/orders", {
      method: "POST",
      body: { items: cart.map((l) => ({ id_variante: l.id_variante, cantidad: l.cantidad })) },
    });
    cart = [];
    saveCart();
    toast("Pedido creado. Tenés 15 minutos para pagarlo.");
    location.hash = "#cuenta";
  });

  button.disabled = false;
}

let searchTimer;
$("#f-q").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { shop.page = 1; run(loadTienda); }, 350);
});
$("#f-cat").addEventListener("change", () => { shop.page = 1; run(loadTienda); });
$("#f-tipo").addEventListener("change", () => { shop.page = 1; run(loadTienda); });

/* ---------- Calendario ---------- */
async function loadCalendario() {
  eventsCache = null;
  const events = await getEvents();
  const box = $("#calendar");
  box.replaceChildren();

  if (!events.length) {
    box.append(h("p", { class: "empty" }, "No hay actividades cargadas todavía."));
    return;
  }

  const now = new Date();
  let lastMonth = "";

  for (const e of events) {
    const start = new Date(e.fecha_inicio);
    const month = start.toLocaleDateString("es-AR", { month: "long", year: "numeric" });

    if (month !== lastMonth) {
      box.append(h("h2", { class: "month" }, month));
      lastMonth = month;
    }

    box.append(h("article", { class: `event${new Date(e.fecha_fin) < now ? " past" : ""}` },
      h("div", { class: "day" }, String(start.getDate()),
        h("small", {}, start.toLocaleDateString("es-AR", { month: "short" }))),
      h("div", {},
        h("h3", {}, e.titulo),
        h("span", { class: "tag" }, e.tipo),
        h("p", { class: "muted" }, `${fdate(e.fecha_inicio)} a ${new Date(e.fecha_fin).toLocaleTimeString("es-AR", { timeStyle: "short" })} - ${e.espacio}`),
        e.descripcion ? h("p", {}, e.descripcion) : null,
      ),
    ));
  }
}

/* ---------- Mi cuenta ---------- */
const account = { all: false };

async function loadCuenta() {
  const box = $("#account");
  box.replaceChildren();

  if (!user) {
    box.append(h("p", { class: "empty" },
      "Ingresá para ver tus datos y tus pedidos. ",
      h("a", { class: "link", href: LOGIN_URL }, "Ir a ingresar")));
    return;
  }

  const me = await api("/auth/me");
  user = me.usuario;
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  renderAuth();

  box.append(h("section", { class: "card" },
    h("h2", {}, `${user.nombre} ${user.apellido}`),
    h("p", { class: "muted" }, user.email),
    h("p", {}, "Roles: ", ...user.roles.map((r) => h("span", { class: "tag" }, r)), " "),
  ));

  if (hasRole(MANAGERS)) await renderInventoryAlerts(box);

  const ordersCard = h("section", { class: "card" }, h("h2", {}, hasRole(MANAGERS) && account.all ? "Todos los pedidos" : "Mis pedidos"));

  if (hasRole(MANAGERS)) {
    ordersCard.append(h("label", { class: "check" },
      h("input", {
        type: "checkbox", checked: account.all,
        onchange: (event) => { account.all = event.target.checked; run(loadCuenta); },
      }),
      " Ver pedidos de todos los usuarios"));
  }

  const params = new URLSearchParams({ per_page: 20 });
  if (hasRole(MANAGERS) && account.all) params.set("todos", "true");
  const { pedidos } = await api(`/orders?${params}`);

  if (!pedidos.length) ordersCard.append(h("p", { class: "muted" }, "Todavía no hay pedidos."));
  for (const order of pedidos) ordersCard.append(orderRow(order));

  box.append(ordersCard);
}

async function renderInventoryAlerts(box) {
  const { inventario } = await api("/inventory?max_stock=5&per_page=20");
  const card = h("section", { class: "card" }, h("h2", {}, "Stock crítico (5 o menos)"));

  if (!inventario.length) {
    card.append(h("p", { class: "muted" }, "No hay productos con stock crítico."));
  } else {
    card.append(h("table", { class: "inv" },
      h("thead", {}, h("tr", {}, h("th", {}, "Producto"), h("th", {}, "Opción"), h("th", {}, "Stock"))),
      h("tbody", {}, inventario.map((row) => h("tr", {},
        h("td", {}, row.producto), h("td", {}, row.variante),
        h("td", { class: "low" }, String(row.stock)))))));
  }
  box.append(card);
}

function orderRow(order) {
  const detail = h("div", { hidden: true });
  const actions = h("div", { class: "actions" });
  const reload = () => run(loadCuenta);

  const row = h("div", { class: "order" },
    h("div", { class: "order-head" },
      h("strong", {}, `Pedido n.º ${order.id_pedido}`),
      h("span", { class: `tag ${order.estado}` }, ESTADOS[order.estado] || order.estado),
      h("small", { class: "muted" }, fdate(order.fecha_creacion)),
    ),
    order.estado === "PENDING" && order.fecha_vencimiento_reserva
      ? h("small", { class: "muted" }, `Reserva hasta ${fdate(order.fecha_vencimiento_reserva)}`)
      : null,
    actions,
    detail,
  );

  actions.append(h("button", {
    class: "btn ghost small", type: "button",
    onclick: () => run(async () => {
      if (!detail.hidden) { detail.hidden = true; return; }
      const { pedido } = await api(`/orders/${order.id_pedido}`);
      detail.replaceChildren(
        h("ul", {}, pedido.detalles.map((d) =>
          h("li", {}, `${d.cantidad} x ${d.producto} (${d.variante}) - ${money(d.precio_unitario)}`))),
        h("p", {}, h("strong", {}, `Total: ${money(pedido.total)}`)),
      );
      detail.hidden = false;
    }),
  }, "Ver detalle"));

  const isOwner = user && order.id_usuario === user.id_usuario;

  if (order.estado === "PENDING" && isOwner) {
    actions.append(
      h("button", { class: "btn small", type: "button", onclick: () => run(() => payOrder(order, "APPROVED").then(reload)) }, "Pagar (simulado)"),
      h("button", { class: "btn ghost small", type: "button", onclick: () => run(() => payOrder(order, "REJECTED").then(reload)) }, "Simular rechazo"),
      h("button", {
        class: "btn danger small", type: "button",
        onclick: () => run(async () => {
          await api(`/orders/${order.id_pedido}/cancel`, { method: "POST" });
          toast("Pedido cancelado.");
          await loadCuenta();
        }),
      }, "Cancelar"),
    );
  }

  if (hasRole(MANAGERS) && ["APPROVED", "READY"].includes(order.estado)) {
    const target = order.estado === "APPROVED" ? "READY" : "DELIVERED";
    actions.append(h("button", {
      class: "btn small", type: "button",
      onclick: () => run(async () => {
        await api(`/orders/${order.id_pedido}/status`, { method: "PATCH", body: { estado: target } });
        toast(target === "READY" ? "Pedido listo para retirar." : "Pedido entregado.");
        await loadCuenta();
      }),
    }, target === "READY" ? "Marcar como listo" : "Marcar como entregado"));
  }

  return row;
}

// Pago simulado: crea el intento de pago (si no existe) y lo resuelve.
async function payOrder(order, result) {
  const { pedido } = await api(`/orders/${order.id_pedido}`);
  let paymentId = pedido.pagos.length ? pedido.pagos[0].id_pago : null;

  if (!paymentId) {
    const created = await api(`/orders/${order.id_pedido}/payments`, {
      method: "POST",
      body: { metodo: "MERCADO_PAGO" },
    });
    paymentId = created.pago.id_pago;
  }

  await api(`/payments/${paymentId}/simulate`, { method: "POST", body: { estado: result } });
  toast(result === "APPROVED" ? "Pago aprobado." : "Pago rechazado: devolvimos el stock.", result !== "APPROVED");
}

/* ---------- Inicio ---------- */
renderAuth();
renderCart();
window.addEventListener("hashchange", route);
route();