import { tieneGmailConectado, tieneSesionActiva } from "./autenticacion.js";

const paginas = new Set([
  "inicio", "como-funciona", "campana", "correo", "confirmacion", "espera", "progreso", "resultados",
  "planes", "pago", "pago-enviado", "nosotros", "privacidad", "cookies", "terminos", "administracion",
]);
let accesoComprobado = false;

function necesitaAcceso(ruta) {
  return ruta === "campana" && (!tieneSesionActiva() || !tieneGmailConectado());
}

function iniciarAccesoCampana() {
  window.location.assign("/api/v1/autenticacion/google/iniciar?destino=campana");
}

export function rutaActual() {
  const ruta = window.location.hash.slice(1);
  return paginas.has(ruta) ? ruta : "inicio";
}

export function irA(ruta) {
  window.location.hash = ruta;
  if (rutaActual() === ruta) mostrarRuta();
}

export function mostrarRuta() {
  const ruta = rutaActual();
  if (accesoComprobado && necesitaAcceso(ruta)) {
    iniciarAccesoCampana();
    return;
  }
  const visible = ruta === "campana" && !accesoComprobado ? "inicio" : ruta;
  document.querySelectorAll("[data-pagina]").forEach((pagina) => {
    pagina.hidden = pagina.id !== visible;
  });
  document.querySelectorAll("[data-enlace-ruta]").forEach((enlace) => {
    if (enlace.dataset.enlaceRuta === visible) enlace.setAttribute("aria-current", "page");
    else enlace.removeAttribute("aria-current");
  });
  document.title = `${document.querySelector(`#${visible} h1`)?.textContent ?? "DEBUPA"} | DEBUPA`;
  window.scrollTo({ top: 0, behavior: "instant" });
}

export function configurarRutas() {
  document.addEventListener("click", (evento) => {
    const enlace = evento.target.closest('a[href="#campana"]');
    if (!enlace || !necesitaAcceso("campana")) return;
    evento.preventDefault();
    iniciarAccesoCampana();
  });
  window.addEventListener("debupa:cuenta-actualizada", () => {
    accesoComprobado = true;
    if (rutaActual() === "campana") mostrarRuta();
  });
  window.addEventListener("hashchange", mostrarRuta);
  mostrarRuta();
}
