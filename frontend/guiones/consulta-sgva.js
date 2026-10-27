import { estadoAplicacion } from "./estado-aplicacion.js";

const teclasEdicion = new Set(["Backspace", "Delete", "ArrowLeft", "ArrowRight", "Home", "End", "Tab"]);

function configurarDocumento() {
  const documento = document.querySelector("#numero-documento");
  documento.pattern = "[0-9]{5,15}";
  documento.maxLength = 15;
  documento.placeholder = "Tu número de documento";
  documento.nextElementSibling.textContent = "Se usa solo durante la consulta.";

  documento.addEventListener("input", () => {
    const posicion = documento.selectionStart;
    documento.value = documento.value.replace(/[^0-9]/g, "").slice(0, 15);
    if (posicion === null) return;
    const destino = Math.min(posicion, documento.value.length);
    documento.setSelectionRange(destino, destino);
  });
  documento.addEventListener("keydown", (evento) => {
    if (evento.ctrlKey || evento.metaKey || evento.altKey) return;
    if (!/^\d$/.test(evento.key) && !teclasEdicion.has(evento.key)) evento.preventDefault();
  });
  documento.addEventListener("paste", (evento) => {
    if (/[^0-9]/.test(evento.clipboardData?.getData("text") ?? "")) evento.preventDefault();
  });
}

export async function configurarConsultaSgva() {
  let capacidades;
  try {
    const respuesta = await fetch("/api/v1/capacidades", { cache: "no-store" });
    if (!respuesta.ok) return;
    capacidades = await respuesta.json();
  } catch {
    // Sin conexión, la vista de demostración sigue disponible.
    return;
  }

  estadoAplicacion.consultaSgvaActiva = capacidades.sgva === true;
  if (!estadoAplicacion.consultaSgvaActiva) return;
  document.querySelector(".aviso_prototipo").textContent = "Los mensajes a empresas salen de tu Gmail tras tu confirmación. El resumen llega desde debupawebapp@gmail.com.";
  document.querySelector("#como-funciona .paso_tarjeta:last-child p").textContent = "Los mensajes autorizados saldrán desde tu Gmail. DEBUPA enviará el resumen de contactos desde su correo; el historial evita recontactos durante seis meses.";
  const opcionIa = document.querySelector("#opcion-ia");
  const aceptarIa = document.querySelector("#aceptar-ia");
  // Cuando Gemini está habilitado, la autorización es obligatoria tanto en la vista como en la API.
  opcionIa.hidden = capacidades.clasificacion_ia !== true;
  aceptarIa.required = capacidades.clasificacion_ia === true;
  const documento = document.querySelector("#numero-documento");
  const clave = document.querySelector("#clave-sgva");
  for (const campo of [documento, clave]) {
    campo.disabled = false;
    campo.required = true;
  }
  configurarDocumento();
  clave.placeholder = "Tu contraseña de SGVA";
  clave.nextElementSibling.textContent = "Se borra del formulario al iniciar y no se guarda en la base de datos.";
  document.querySelector("#formulario-correo button[type='submit']").textContent = "Consultar ofertas en SGVA";
  document.querySelector(".correo_borrador").textContent = "Se enviará solo tras tu confirmación";
  document.querySelector("#progreso .progreso_principal .ceja").textContent = "Consulta de SGVA";
  document.querySelector("#progreso h1").textContent = "Buscando ofertas visibles para ti.";
  document.querySelector("#progreso .panel_ayuda_progreso p").textContent = "Las consultas esperan su turno y su estado permanece disponible en tu cuenta mientras el servidor siga activo.";
  document.querySelector("#progreso .nota_fina").textContent = "Se lee SGVA sin postularte y sin enviar correos.";
  document.querySelector("#campana .aviso_requisitos small").textContent = "DEBUPA todavía no puede comprobar por sí solo si tienes patrocinio o una postulación activa.";
  document.querySelector("#campana .grupo_campo .ayuda_grupo").textContent = "Introduce tus credenciales una vez por consulta; se descartan al terminar y no se guardan en la base de datos.";
}

