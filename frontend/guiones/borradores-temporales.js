import { borrarContenidoTemporal } from "./campanas.js";

const panel = document.querySelector("#borradores-temporales");
const lista = document.querySelector("#lista-borradores-temporales");
const estado = document.querySelector("#estado-borradores-temporales");
let sesionActiva = false;
let version = 0;

async function actualizarBorradores() {
  const consulta = ++version;
  try {
    const respuesta = await fetch("/api/v1/contenidos-temporales", { cache: "no-store", credentials: "same-origin" });
    if (!respuesta.ok) throw new Error("No pudimos consultar tus borradores.");
    const borradores = await respuesta.json();
    if (consulta !== version || !sesionActiva) return;
    lista.replaceChildren();
    panel.hidden = borradores.length === 0;
    estado.textContent = "";
    borradores.forEach((borrador) => {
      const elemento = document.createElement("li");
      const detalle = document.createElement("span");
      const fecha = new Date(borrador.vence_en).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
      const cantidadArchivos = borrador.archivos.length;
      const nombreArchivos = cantidadArchivos === 1 ? "adjunto" : "adjuntos";
      detalle.textContent = `Borrador ${borrador.campana_id.slice(0, 8)} · vence ${fecha} · ${cantidadArchivos} ${nombreArchivos}`;
      const boton = document.createElement("button");
      boton.className = "boton boton_secundario boton_pequeno";
      boton.type = "button";
      boton.textContent = "Eliminar";
      boton.addEventListener("click", async () => {
        boton.disabled = true;
        estado.textContent = "Eliminando borrador…";
        try {
          await borrarContenidoTemporal(borrador.campana_id);
          window.dispatchEvent(new CustomEvent("debupa:contenidos-actualizados", {
            detail: { campanaId: borrador.campana_id, accion: "borrado" },
          }));
        } catch (error) {
          estado.textContent = error instanceof Error ? error.message : "No se pudo eliminar el borrador.";
          boton.disabled = false;
        }
      });
      elemento.append(detalle, boton);
      lista.append(elemento);
    });
  } catch {
    if (consulta === version && sesionActiva) estado.textContent = "No pudimos consultar tus borradores.";
  }
}

export function configurarBorradoresTemporales() {
  window.addEventListener("debupa:cuenta-actualizada", (evento) => {
    sesionActiva = Boolean(evento.detail);
    if (sesionActiva) actualizarBorradores();
    else {
      version += 1;
      panel.hidden = true;
      lista.replaceChildren();
      estado.textContent = "";
    }
  });
  window.addEventListener("debupa:contenidos-actualizados", () => {
    if (sesionActiva) actualizarBorradores();
  });
}
