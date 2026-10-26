"use strict";

import { enviarConCsrf } from "./autenticacion.js";
import { mensajeVacio, pintarGraficas } from "./graficas-administracion.js";
import { irA } from "./rutas.js";

const estadoPago = document.querySelector("#estado-pago");
const estadoAdmin = document.querySelector("#admin-estado");
let cuenta = null;
let archivoOptimizado = null;
let enlaceComprobante = null;
let metricas = null;
let temporizadorNotificacion = null;
let temporizadorSalida = null;

function notificarAdministracion(mensaje, esError = false) {
  const aviso = document.querySelector("#admin-notificacion");
  clearTimeout(temporizadorNotificacion);
  clearTimeout(temporizadorSalida);
  aviso.textContent = mensaje;
  aviso.setAttribute("role", esError ? "alert" : "status");
  aviso.hidden = false;
  aviso.classList.remove("admin_notificacion_visible");
  requestAnimationFrame(() => {
    requestAnimationFrame(() => aviso.classList.add("admin_notificacion_visible"));
  });
  temporizadorNotificacion = setTimeout(() => {
    aviso.classList.remove("admin_notificacion_visible");
    temporizadorSalida = setTimeout(() => { aviso.hidden = true; }, 240);
  }, 3000);
}

function confirmarDecision(nombre, aprobar) {
  const dialogo = document.querySelector("#confirmar-decision");
  document.querySelector("#titulo-confirmar-decision").textContent = aprobar
    ? "Aceptar solicitud Premium" : "Rechazar solicitud Premium";
  document.querySelector("#texto-confirmar-decision").textContent = aprobar
    ? `Confirma primero el movimiento real en Nequi antes de activar Premium para ${nombre}.`
    : `Se eliminará el comprobante de ${nombre} y se enviará el aviso sobre los 7 días para solicitar reembolso.`;
  const boton = document.querySelector("#aceptar-decision");
  boton.textContent = aprobar ? "Aceptar solicitud" : "Rechazar solicitud";
  boton.classList.toggle("boton_rechazar", !aprobar);
  dialogo.returnValue = "";
  dialogo.showModal();
  return new Promise((resolver) => {
    dialogo.addEventListener("close", () => resolver(dialogo.returnValue === "confirmar"), { once: true });
  });
}

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
  const ver = document.createElement("button");
  ver.className = "boton boton_secundario";
  ver.type = "button";
  ver.textContent = "Ver comprobante";
  ver.addEventListener("click", () => abrirComprobante(solicitud));
  acciones.append(ver);
  for (const [texto, aprobar] of [["Aceptar", true], ["Rechazar", false]]) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = aprobar ? "boton" : "boton boton_rechazar";
    boton.textContent = texto;
    boton.addEventListener("click", async () => {
      if (!await confirmarDecision(solicitud.nombre, aprobar)) return;
      acciones.querySelectorAll("button").forEach((control) => { control.disabled = true; });
      try {
        const respuesta = await enviarConCsrf(`/api/v1/administracion/pagos/${encodeURIComponent(solicitud.id)}/decision`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ aprobar }),
        });
        const resultado = await leerRespuesta(respuesta);
        notificarAdministracion(resultado.notificacion_estado === "enviado"
          ? "Decisión guardada y correo confirmado por Gmail."
          : "Decisión guardada. El correo no quedó confirmado; revisa la cuenta DEBUPA.",
        resultado.notificacion_estado !== "enviado");
        await cargarAdministracion();
      } catch (error) {
        notificarAdministracion(error.message, true);
        acciones.querySelectorAll("button").forEach((control) => { control.disabled = false; });
      }
    });
    acciones.append(boton);
  }
  datos.append(nombre, correo, fecha, acciones);
  tarjeta.append(datos);
  return tarjeta;
}

async function abrirComprobante(solicitud) {
  const visor = document.querySelector("#visor-comprobante");
  const imagen = document.querySelector("#imagen-comprobante");
  const pdf = document.querySelector("#pdf-comprobante");
  const enlacePdf = document.querySelector("#abrir-pdf-comprobante");
  try {
    const respuesta = await fetch(`/api/v1/administracion/pagos/${encodeURIComponent(solicitud.id)}/comprobante`, { cache: "no-store" });
    if (!respuesta.ok) throw new Error("El comprobante ya no está disponible.");
    const archivo = await respuesta.blob();
    if (!["image/png", "image/jpeg", "application/pdf"].includes(archivo.type)) {
      throw new Error("El formato del comprobante no se puede mostrar.");
    }
    limpiarComprobante();
    enlaceComprobante = URL.createObjectURL(archivo);
    if (archivo.type === "application/pdf") {
      pdf.src = enlaceComprobante;
      enlacePdf.href = enlaceComprobante;
      pdf.hidden = false;
      enlacePdf.hidden = false;
    } else {
      imagen.src = enlaceComprobante;
      imagen.alt = `Comprobante enviado por ${solicitud.nombre}`;
      imagen.hidden = false;
    }
    visor.showModal();
  } catch (error) {
    notificarAdministracion(error.message, true);
  }
}

function cerrarComprobante() {
  document.querySelector("#visor-comprobante").close();
}

function limpiarComprobante() {
  const imagen = document.querySelector("#imagen-comprobante");
  const pdf = document.querySelector("#pdf-comprobante");
  const enlacePdf = document.querySelector("#abrir-pdf-comprobante");
  imagen.hidden = true;
  imagen.removeAttribute("src");
  pdf.hidden = true;
  pdf.removeAttribute("src");
  enlacePdf.hidden = true;
  enlacePdf.removeAttribute("href");
  if (enlaceComprobante) URL.revokeObjectURL(enlaceComprobante);
  enlaceComprobante = null;
}

function pintarMetricas() {
  if (!metricas) return;
  const ingresos = document.querySelector("#admin-periodo-ingresos").value;
  const campanas = document.querySelector("#admin-periodo-campanas").value;
  const moneda = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
  document.querySelector("#admin-ingresos").textContent = moneda.format(metricas.periodos[ingresos].ingresos_aprobados_cop);
  document.querySelector("#admin-campanas").textContent = String(metricas.periodos[campanas].campanas);
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
        notificarAdministracion(
          resultado.notificacion_estado === "enviado"
            ? "Gmail confirmó el aviso." : "Gmail no confirmó el aviso. Revisa la conexión de DEBUPA.",
          resultado.notificacion_estado !== "enviado",
        );
        await cargarAdministracion();
      } catch (error) {
        notificarAdministracion(error.message, true);
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
    document.querySelector("#admin-cuenta").textContent = "DEBUPA";
    metricas = datos;
    pintarMetricas();
    pintarGraficas(datos);
    document.querySelector("#admin-correo").textContent = datos.correo_servicio_conectado
      ? "Permiso guardado. Comprueba que Gmail pueda enviar con la prueba." : "Sin conexión de servicio. Entra con la cuenta DEBUPA.";
    const lista = document.querySelector("#lista-solicitudes");
    lista.replaceChildren(...datos.solicitudes.map(mostrarSolicitud));
    document.querySelector("#admin-cantidad-solicitudes").textContent = `${datos.solicitudes.length} pendientes`;
    if (!datos.solicitudes.length) lista.replaceChildren(mensajeVacio("No hay solicitudes por revisar. Las nuevas aparecerán aquí.", true));
    const avisos = document.querySelector("#lista-avisos");
    avisos.replaceChildren(...datos.avisos_pendientes.map(mostrarAviso));
    document.querySelector("#admin-avisos").hidden = !datos.avisos_pendientes.length;
  } catch (error) {
    estadoAdmin.textContent = error.message;
  }
}

async function optimizarImagen(archivo) {
  if (!archivo || !["image/png", "image/jpeg"].includes(archivo.type) || archivo.size > 8 * 1024 * 1024) {
    throw new Error("Elige una captura PNG o JPG de máximo 8 MB.");
  }
  const original = await createImageBitmap(archivo);
  const escala = Math.min(1, 1800 / Math.max(original.width, original.height));
  const lienzo = document.createElement("canvas");
  lienzo.width = Math.round(original.width * escala);
  lienzo.height = Math.round(original.height * escala);
  const contexto = lienzo.getContext("2d");
  contexto.fillStyle = "#ffffff";
  contexto.fillRect(0, 0, lienzo.width, lienzo.height);
  contexto.drawImage(original, 0, 0, lienzo.width, lienzo.height);
  original.close();
  const convertir = (calidad) => new Promise((listo) => lienzo.toBlob(listo, "image/jpeg", calidad));
  let resultado = await convertir(0.88);
  if (resultado?.size > 2 * 1024 * 1024) resultado = await convertir(0.72);
  if (!resultado || resultado.size > 2 * 1024 * 1024) throw new Error("La imagen sigue pesando más de 2 MB. Prueba otra captura.");
  return new File([resultado], "comprobante-optimizado.jpg", { type: "image/jpeg" });
}

async function prepararComprobante(archivo) {
  if (archivo?.type === "application/pdf") {
    if (!archivo.size || archivo.size > 2 * 1024 * 1024) {
      throw new Error("El PDF debe pesar como máximo 2 MB.");
    }
    return archivo;
  }
  return optimizarImagen(archivo);
}

function avisoSinComprobante() {
  document.querySelector("#aviso-comprobante").showModal();
}

export function configurarPremium() {
  document.querySelector("#cancelar-decision").addEventListener("click", () => {
    document.querySelector("#confirmar-decision").close("cancelar");
  });
  document.querySelector("#aceptar-decision").addEventListener("click", () => {
    document.querySelector("#confirmar-decision").close("confirmar");
  });
  document.querySelector("#imagen-comprobante").addEventListener("error", () => {
    if (document.querySelector("#visor-comprobante").open) {
      cerrarComprobante();
      notificarAdministracion("No se pudo mostrar la imagen. Adjunta otra captura o un PDF legible.", true);
    }
  });
  document.querySelector("#admin-periodo-ingresos").addEventListener("change", pintarMetricas);
  document.querySelector("#admin-periodo-campanas").addEventListener("change", pintarMetricas);
  document.querySelector("#cerrar-visor-comprobante").addEventListener("click", cerrarComprobante);
  document.querySelector("#visor-comprobante").addEventListener("close", limpiarComprobante);
  document.querySelector("#seguir-en-pago").addEventListener("click", () => {
    document.querySelector("#aviso-comprobante").close();
    document.querySelector("#comprobante-pago").click();
  });
  document.addEventListener("click", (evento) => {
    const enlace = evento.target.closest("a[href^='#']");
    if (window.location.hash !== "#pago" || !enlace || enlace.target === "_blank" || enlace.id === "salir-de-pago" || archivoOptimizado) return;
    evento.preventDefault();
    document.querySelector("#salir-de-pago").href = enlace.getAttribute("href");
    avisoSinComprobante();
  });
  document.querySelector("#salir-de-pago").addEventListener("click", () => document.querySelector("#aviso-comprobante").close());
  document.querySelector("#comprobante-pago").addEventListener("change", async (evento) => {
    archivoOptimizado = null;
    const archivo = evento.target.files[0];
    if (!archivo) return;
    estadoPago.textContent = archivo.type === "application/pdf" ? "Validando PDF…" : "Optimizando imagen…";
    try {
      archivoOptimizado = await prepararComprobante(archivo);
      document.querySelector("#nombre-comprobante").textContent = `${archivo.name} · ${(archivoOptimizado.size / 1024).toFixed(0)} KB listos`;
      estadoPago.textContent = "Comprobante listo para enviar.";
    } catch (error) {
      evento.target.value = "";
      document.querySelector("#nombre-comprobante").textContent = "Elegir PNG, JPG o PDF";
      estadoPago.textContent = error.message;
    }
  });
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
    if (!archivoOptimizado) {
      estadoPago.textContent = "Adjunta un comprobante legible para solicitar la revisión.";
      avisoSinComprobante();
      return;
    }
    if (!document.querySelector("#aceptar-condiciones-pago").checked) {
      estadoPago.textContent = "Acepta los términos y el tratamiento de datos para continuar.";
      document.querySelector("#aceptar-condiciones-pago").focus();
      return;
    }
    const boton = evento.currentTarget.querySelector("button[type='submit']");
    boton.disabled = true;
    estadoPago.textContent = "Enviando comprobante…";
    try {
      const datos = new FormData();
      datos.set("comprobante", archivoOptimizado);
      datos.set("acepta_condiciones", "true");
      await leerRespuesta(await enviarConCsrf("/api/v1/pagos-premium", { method: "POST", body: datos }));
      evento.currentTarget.reset();
      archivoOptimizado = null;
      document.querySelector("#nombre-comprobante").textContent = "Elegir PNG, JPG o PDF";
      irA("pago-enviado");
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
