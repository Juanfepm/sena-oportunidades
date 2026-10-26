"use strict";

import { enviarConCsrf } from "./autenticacion.js";

const estadoPago = document.querySelector("#estado-pago");
const estadoAdmin = document.querySelector("#admin-estado");
let cuenta = null;

async function leerRespuesta(respuesta) {
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) throw new Error(typeof datos.detail === "string" ? datos.detail : "No fue posible completar la solicitud.");
  return datos;
}

async function cargarPago() {
  if (!cuenta) return;
  try {
    const datos = await leerRespuesta(await fetch("/api/v1/pagos-premium/estado", { cache: "no-store" }));
    const formulario = document.querySelector("#formulario-pago");
    formulario.querySelector("button[type='submit']").disabled = datos.estado === "pendiente";
    if (datos.estado === "pendiente") estadoPago.textContent = "Tu comprobante está pendiente de revisión manual. Te avisaremos por correo.";
    else if (datos.plan === "premium" && datos.premium_hasta) {
      estadoPago.textContent = `Premium activo hasta el ${new Date(datos.premium_hasta).toLocaleDateString("es-CO")}. Puedes renovar con un nuevo pago.`;
    } else if (datos.estado === "rechazado") estadoPago.textContent = "La solicitud anterior no se aprobó. Puedes adjuntar otro comprobante.";
    else estadoPago.textContent = "Aún no has solicitado una activación Premium.";
  } catch (error) {
    estadoPago.textContent = error.message;
  }
}

function mostrarSolicitud(solicitud) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "solicitud_premium";
  const datos = document.createElement("div");
  const nombre = document.createElement("h3");
  nombre.textContent = solicitud.nombre;
  const correo = document.createElement("p");
  correo.textContent = solicitud.correo;
  const fecha = document.createElement("small");
  fecha.textContent = new Date(solicitud.creado_en).toLocaleString("es-CO");
  const acciones = document.createElement("div");
  acciones.className = "solicitud_premium_acciones";
  for (const [texto, aprobar] of [["Aprobar", true], ["Rechazar", false]]) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = aprobar ? "boton" : "boton boton_secundario";
    boton.textContent = texto;
    boton.addEventListener("click", async () => {
      if (!window.confirm(`${texto} la solicitud de ${solicitud.nombre}? Confirma primero el movimiento real en Nequi.`)) return;
      acciones.querySelectorAll("button").forEach((control) => { control.disabled = true; });
      try {
        const respuesta = await enviarConCsrf(`/api/v1/administracion/pagos/${encodeURIComponent(solicitud.id)}/decision`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ aprobar }),
        });
        const resultado = await leerRespuesta(respuesta);
        estadoAdmin.textContent = resultado.notificacion_estado === "enviado"
          ? "Decisión guardada y correo confirmado por Gmail."
          : "Decisión guardada. El correo no quedó confirmado; revisa la cuenta DEBUPA.";
        await cargarAdministracion();
      } catch (error) {
        estadoAdmin.textContent = error.message;
        acciones.querySelectorAll("button").forEach((control) => { control.disabled = false; });
      }
    });
    acciones.append(boton);
  }
  datos.append(nombre, correo, fecha, acciones);
  const imagen = document.createElement("img");
  imagen.alt = `Comprobante enviado por ${solicitud.nombre}`;
  imagen.loading = "lazy";
  imagen.src = `/api/v1/administracion/pagos/${encodeURIComponent(solicitud.id)}/comprobante`;
  tarjeta.append(datos, imagen);
  return tarjeta;
}

function mostrarAviso(aviso) {
  const fila = document.createElement("p");
  const correo = document.createElement("strong");
  correo.textContent = aviso.correo;
  fila.append(correo, document.createTextNode(aviso.estado === "pendiente"
    ? " · El correo está pendiente. " : " · Revisa Enviados antes de reenviar."));
  if (aviso.estado === "pendiente") {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "boton boton_secundario";
    boton.textContent = "Enviar aviso";
    boton.addEventListener("click", async () => {
      boton.disabled = true;
      try {
        const respuesta = await enviarConCsrf(`/api/v1/administracion/pagos/${encodeURIComponent(aviso.id)}/notificar`, { method: "POST" });
        const resultado = await leerRespuesta(respuesta);
        estadoAdmin.textContent = resultado.notificacion_estado === "enviado"
          ? "Gmail confirmó el aviso." : "Gmail no confirmó el aviso. Revisa la conexión de DEBUPA.";
        await cargarAdministracion();
      } catch (error) {
        estadoAdmin.textContent = error.message;
        boton.disabled = false;
      }
    });
    fila.append(boton);
  }
  return fila;
}

async function cargarAdministracion() {
  if (!cuenta?.es_administrador) return;
  try {
    const datos = await leerRespuesta(await fetch("/api/v1/administracion/resumen", { cache: "no-store" }));
    document.querySelector("#admin-total").textContent = String(datos.usuarios);
    document.querySelector("#admin-gratis").textContent = String(datos.gratis);
    document.querySelector("#admin-premium").textContent = String(datos.premium);
    document.querySelector("#admin-correo").textContent = datos.correo_servicio_conectado
      ? "Permiso guardado. Comprueba que Gmail pueda enviar con la prueba." : "Sin conexión de servicio. Entra con la cuenta DEBUPA.";
    const lista = document.querySelector("#lista-solicitudes");
    lista.replaceChildren(...datos.solicitudes.map(mostrarSolicitud));
    if (!datos.solicitudes.length) lista.textContent = "No hay solicitudes por revisar.";
    const avisos = document.querySelector("#lista-avisos");
    avisos.replaceChildren(...datos.avisos_pendientes.map(mostrarAviso));
    if (!datos.avisos_pendientes.length) avisos.textContent = "Todos los avisos quedaron confirmados.";
  } catch (error) {
    estadoAdmin.textContent = error.message;
  }
}

export function configurarPremium() {
  window.addEventListener("debupa:cuenta-actualizada", (evento) => {
    cuenta = evento.detail;
    document.querySelector("#enlace-administracion").hidden = !cuenta?.es_administrador;
    if (cuenta) cargarPago();
    if (cuenta?.es_administrador) cargarAdministracion();
  });
  window.addEventListener("hashchange", () => {
    if (window.location.hash === "#pago") cargarPago();
    if (window.location.hash === "#administracion") cargarAdministracion();
  });
  document.querySelector("#formulario-pago").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!cuenta) { estadoPago.textContent = "Inicia sesión con Google antes de enviar el comprobante."; return; }
    const archivo = document.querySelector("#comprobante-pago").files[0];
    if (!archivo || !["image/png", "image/jpeg"].includes(archivo.type) || archivo.size > 2 * 1024 * 1024) {
      estadoPago.textContent = "Elige una captura PNG o JPG de máximo 2 MB.";
      return;
    }
    const boton = evento.currentTarget.querySelector("button[type='submit']");
    boton.disabled = true;
    estadoPago.textContent = "Enviando comprobante…";
    try {
      const datos = new FormData();
      datos.set("comprobante", archivo);
      await leerRespuesta(await enviarConCsrf("/api/v1/pagos-premium", { method: "POST", body: datos }));
      evento.currentTarget.reset();
      estadoPago.textContent = "Recibimos el comprobante. La activación se revisará manualmente.";
    } catch (error) {
      estadoPago.textContent = error.message;
      boton.disabled = false;
    }
  });
  document.querySelector("#admin-probar-correo").addEventListener("click", async (evento) => {
    const boton = evento.currentTarget;
    boton.disabled = true;
    estadoAdmin.textContent = "Enviando prueba a la cuenta DEBUPA…";
    try {
      await leerRespuesta(await enviarConCsrf("/api/v1/administracion/correo/prueba", { method: "POST" }));
      estadoAdmin.textContent = "Gmail confirmó la prueba. Revisa Recibidos y Enviados de DEBUPA.";
    } catch (error) {
      estadoAdmin.textContent = error.message;
    } finally {
      boton.disabled = false;
    }
  });
}
