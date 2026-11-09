const estadoCuenta = document.querySelector("#estado-cuenta");
const enlaceGoogle = document.querySelector("#iniciar-google");
const botonCerrar = document.querySelector("#cerrar-sesion");
const estadoGmail = document.querySelector("#estado-gmail");
let cuentaActiva = null;
let gmailConectado = false;
let pruebaGmailSolicitada = false;
let tokenCsrf = null;

function actualizarPlan(plan) {
  const selector = document.querySelector("#plan-campana");
  const opcionPremium = selector.querySelector('option[value="premium"]');
  opcionPremium.disabled = plan !== "premium";
  opcionPremium.textContent = plan === "premium" ? "Premium · activo" : "Premium · pendiente de activación";
  selector.value = plan === "premium" ? "premium" : "gratis";
  selector.dispatchEvent(new Event("change"));
  selector.disabled = plan === "premium";
  document.querySelector("#detalle-plan-campana").textContent = plan === "premium"
    ? "Premium activo para esta campaña. El plan se asigna desde tu cuenta."
    : "El plan premium se activará tras la verificación del pago.";
}

async function obtenerJson(ruta) {
  const respuesta = await fetch(ruta, { cache: "no-store", credentials: "same-origin" });
  if (respuesta.status >= 500) {
    const datos = await respuesta.json().catch(() => ({}));
    const error = new Error("El servicio no está disponible.");
    error.tipo = datos.codigo === "base_datos" ? "base-datos" : "servicio";
    throw error;
  }
  if (!respuesta.ok) return { codigo: respuesta.status, datos: null };
  return { codigo: respuesta.status, datos: await respuesta.json() };
}

function ocultarGmail() {
  gmailConectado = false;
  pruebaGmailSolicitada = false;
  estadoGmail.hidden = true;
}

async function actualizarGmail() {
  const [capacidades, gmail] = await Promise.all([
    obtenerJson("/api/v1/capacidades"),
    obtenerJson("/api/v1/gmail/estado"),
  ]);
  if (capacidades.datos?.gmail !== true) {
    ocultarGmail();
    return;
  }
  estadoGmail.hidden = false;
  pruebaGmailSolicitada = gmail.datos?.prueba_solicitada === true;
  if (gmail.datos?.conectado) {
    gmailConectado = true;
    estadoGmail.textContent = "Gmail conectado";
    estadoGmail.title = gmail.datos.correo ?? "";
    enlaceGoogle.hidden = true;
    return;
  }
  gmailConectado = false;
  estadoGmail.textContent = "Gmail pendiente; vuelve a entrar";
  estadoGmail.removeAttribute("title");
  enlaceGoogle.textContent = "Autorizar Gmail";
  enlaceGoogle.hidden = false;
}

async function actualizarCuenta() {
  try {
    const cuenta = await obtenerJson("/api/v1/autenticacion/yo");
    if (cuenta.datos) {
      cuentaActiva = cuenta.datos;
      actualizarPlan(cuenta.datos.plan);
      const nombre = cuenta.datos.nombre || cuenta.datos.correo;
      estadoCuenta.textContent = `${nombre} · ${cuenta.datos.plan}`;
      estadoCuenta.title = cuenta.datos.correo;
      enlaceGoogle.hidden = true;
      botonCerrar.hidden = false;
      const seguridad = await obtenerJson("/api/v1/autenticacion/csrf");
      tokenCsrf = seguridad.datos?.token ?? null;
      await actualizarGmail();
      window.dispatchEvent(new CustomEvent("debupa:cuenta-actualizada", {
        detail: {
          ...cuentaActiva,
          gmail_conectado: gmailConectado,
          gmail_prueba_solicitada: pruebaGmailSolicitada,
        },
      }));
      return;
    }

    cuentaActiva = null;
    actualizarPlan("gratis");
    tokenCsrf = null;
    ocultarGmail();
    const capacidades = await obtenerJson("/api/v1/capacidades");
    const disponible = capacidades.datos?.google_oauth === true;
    estadoCuenta.textContent = disponible ? "Sin sesión" : "Acceso temporalmente no disponible";
    estadoCuenta.removeAttribute("title");
    enlaceGoogle.textContent = "Entrar con Google";
    enlaceGoogle.hidden = !disponible;
    botonCerrar.hidden = true;
    window.dispatchEvent(new CustomEvent("debupa:cuenta-actualizada", { detail: null }));
  } catch (error) {
    cuentaActiva = null;
    actualizarPlan("gratis");
    tokenCsrf = null;
    ocultarGmail();
    estadoCuenta.textContent = "Abre DEBUPA desde la API para iniciar sesión";
    enlaceGoogle.hidden = true;
    botonCerrar.hidden = true;
    window.dispatchEvent(new CustomEvent("debupa:cuenta-actualizada", { detail: null }));
    if (window.location.pathname === "/") window.location.assign(`/error.html?tipo=${error?.tipo ?? "servicio"}`);
  }
}

export function tieneSesionActiva() {
  return cuentaActiva !== null;
}

export function tieneGmailConectado() {
  return gmailConectado;
}

export async function enviarConCsrf(ruta, opciones = {}) {
  if (!tokenCsrf) await actualizarCuenta();
  if (!tokenCsrf) throw new Error("Inicia sesión con Google para continuar.");
  const encabezados = new Headers(opciones.headers);
  encabezados.set("X-CSRF-Token", tokenCsrf);
  return fetch(ruta, {
    ...opciones,
    headers: encabezados,
    credentials: "same-origin",
  });
}

export function configurarAutenticacion() {
  botonCerrar.addEventListener("click", async () => {
    botonCerrar.disabled = true;
    estadoCuenta.textContent = "Cerrando sesión…";
    try {
      const respuesta = await fetch("/api/v1/autenticacion/cerrar-sesion", {
        method: "POST",
        headers: { "X-CSRF-Token": tokenCsrf ?? "" },
        credentials: "same-origin",
      });
      if (!respuesta.ok) throw new Error("No se pudo cerrar la sesión.");
      if (window.location.hash === "#campana") window.location.hash = "inicio";
      await actualizarCuenta();
    } catch {
      estadoCuenta.textContent = "No se pudo cerrar la sesión. Intenta de nuevo.";
    } finally {
      botonCerrar.disabled = false;
    }
  });
  actualizarCuenta();
}
