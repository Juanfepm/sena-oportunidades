import { enviarConCsrf } from "./autenticacion.js";

const panel = document.querySelector("#prueba-gmail");
const boton = document.querySelector("#enviar-prueba-gmail");
const estado = document.querySelector("#estado-prueba-gmail");
let versionCuenta = 0;

export function configurarPruebaGmail() {
  window.addEventListener("debupa:cuenta-actualizada", async (evento) => {
    const version = ++versionCuenta;
    panel.hidden = true;
    if (!evento.detail?.gmail_conectado) return;
    boton.disabled = evento.detail.gmail_prueba_solicitada === true;
    estado.textContent = boton.disabled ? "Ya solicitaste una prueba en esta sesión." : "";
    try {
      const respuesta = await fetch("/api/v1/capacidades", { cache: "no-store" });
      if (!respuesta.ok) return;
      const capacidades = await respuesta.json();
      if (version === versionCuenta) panel.hidden = capacidades.gmail_prueba !== true;
    } catch {
      if (version === versionCuenta) panel.hidden = true;
    }
  });

  boton.addEventListener("click", async () => {
    boton.disabled = true;
    estado.textContent = "Solicitando la prueba a Gmail…";
    try {
      const respuesta = await enviarConCsrf("/api/v1/gmail/prueba", { method: "POST" });
      const datos = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok) {
        estado.textContent = typeof datos.detail === "string" ? datos.detail : "No se pudo completar la prueba.";
        return;
      }
      estado.textContent = `Gmail confirmó el envío a ${datos.correo}. Revisa Recibidos y Enviados. ID: ${datos.mensaje_id}`;
    } catch {
      estado.textContent = "No recibimos una respuesta. Revisa Enviados antes de repetir la prueba.";
    }
  });
}
