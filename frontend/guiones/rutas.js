const paginas = new Set([
  "inicio", "como-funciona", "campana", "correo", "confirmacion", "espera", "progreso", "resultados",
  "planes", "pago", "pago-enviado", "nosotros", "privacidad", "cookies", "terminos", "administracion",
]);

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
  document.querySelectorAll("[data-pagina]").forEach((pagina) => {
    pagina.hidden = pagina.id !== ruta;
  });
  document.querySelectorAll("[data-enlace-ruta]").forEach((enlace) => {
    if (enlace.dataset.enlaceRuta === ruta) enlace.setAttribute("aria-current", "page");
    else enlace.removeAttribute("aria-current");
  });
  document.title = `${document.querySelector(`#${ruta} h1`)?.textContent ?? "DEBUPA"} | DEBUPA`;
  window.scrollTo({ top: 0, behavior: "instant" });
}

export function configurarRutas() {
  window.addEventListener("hashchange", mostrarRuta);
  mostrarRuta();
}
