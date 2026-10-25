import { enviarConCsrf, tieneSesionActiva } from "./autenticacion.js";

function leerMensajeError(respuesta) {
  return respuesta.json()
    .then((datos) => ({
      codigo: datos.codigo || datos.detail?.codigo || "servicio",
      mensaje: datos.detail?.mensaje || (typeof datos.detail === "string" ? datos.detail : "No se pudo completar la solicitud."),
    }))
    .catch(() => ({ codigo: "servicio", mensaje: "No se pudo completar la solicitud." }));
}

export async function guardarPreferencias(formulario, correosExcluidos) {
  if (!tieneSesionActiva()) {
    throw new Error("Inicia sesión con Google antes de guardar una búsqueda.");
  }

  const modalidad = formulario.elements.modalidad.value;
  const solicitud = {
    modalidad,
    departamento: modalidad === "remoto" ? "todos" : formulario.elements.departamento.value,
    ciudad: modalidad === "remoto" ? "todas" : formulario.elements.ciudad.value || "todas",
    antiguedad_dias: Number(formulario.elements.antiguedad.value),
    permitir_recontacto: formulario.elements.permitir_recontacto.checked,
    correos_excluidos: correosExcluidos,
    mayor_de_edad: formulario.elements.confirmar_mayoria_edad.checked,
    acepta_tratamiento: formulario.elements.aceptar_tratamiento.checked,
  };
  const respuesta = await enviarConCsrf("/api/v1/campanas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(solicitud),
  });
  if (!respuesta.ok) {
    const error = await leerMensajeError(respuesta);
    const paginasServicios = {
      base_datos: "base-datos",
      servicio_no_disponible: "servicio",
      sgva_no_disponible: "sgva",
    };
    const fallo = new Error(error.mensaje);
    fallo.codigo = respuesta.status >= 500 ? "navegando" : error.codigo;
    if (respuesta.status >= 500) {
      window.location.assign(`/error.html?tipo=${paginasServicios[error.codigo] ?? "servicio"}`);
    }
    throw fallo;
  }
  return respuesta.json();
}

export async function guardarContenidoTemporal(campanaId, formularioCampana, formularioCorreo) {
  const datos = new FormData();
  for (const nombre of ["habilidades", "actividades_deseadas", "actividades_no_deseadas"]) {
    datos.set(nombre, formularioCampana.elements[nombre].value);
  }
  for (const nombre of ["asunto", "cuerpo"]) {
    datos.set(nombre, formularioCorreo.elements[nombre].value);
  }
  for (const archivo of formularioCorreo.elements.archivos.files) datos.append("archivos", archivo);
  const respuesta = await enviarConCsrf(`/api/v1/campanas/${encodeURIComponent(campanaId)}/contenido`, {
    method: "PUT",
    body: datos,
  });
  if (!respuesta.ok) throw new Error((await leerMensajeError(respuesta)).mensaje);
  return respuesta.json();
}

export async function borrarContenidoTemporal(campanaId) {
  const respuesta = await enviarConCsrf(`/api/v1/campanas/${encodeURIComponent(campanaId)}/contenido`, {
    method: "DELETE",
  });
  if (!respuesta.ok) throw new Error((await leerMensajeError(respuesta)).mensaje);
}

export async function iniciarCampana(campanaId, acceso = null) {
  const respuesta = await enviarConCsrf(`/api/v1/campanas/${encodeURIComponent(campanaId)}/iniciar`, {
    method: "POST",
    ...(acceso ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(acceso) } : {}),
  });
  if (!respuesta.ok) throw new Error((await leerMensajeError(respuesta)).mensaje);
  return respuesta.json();
}

export async function consultarCampana(campanaId) {
  const respuesta = await fetch(`/api/v1/campanas/${encodeURIComponent(campanaId)}`, {
    credentials: "same-origin", cache: "no-store",
  });
  if (!respuesta.ok) throw new Error((await leerMensajeError(respuesta)).mensaje);
  return respuesta.json();
}

export async function listarCampanas() {
  const respuesta = await fetch("/api/v1/campanas?limite=20", {
    credentials: "same-origin", cache: "no-store",
  });
  if (!respuesta.ok) throw new Error((await leerMensajeError(respuesta)).mensaje);
  return respuesta.json();
}

export async function consultarDestinatarios(campanaId) {
  const respuesta = await fetch(`/api/v1/campanas/${encodeURIComponent(campanaId)}/destinatarios`, {
    credentials: "same-origin", cache: "no-store",
  });
  if (!respuesta.ok) throw new Error((await leerMensajeError(respuesta)).mensaje);
  return respuesta.json();
}
