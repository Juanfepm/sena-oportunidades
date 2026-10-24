import { enviarConCsrf, tieneSesionActiva } from "./autenticacion.js";

function leerMensajeError(respuesta) {
  return respuesta.json()
    .then((datos) => datos.detail?.mensaje || datos.detail || "No se pudieron guardar tus preferencias.")
    .catch(() => "No se pudieron guardar tus preferencias.");
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
  if (!respuesta.ok) throw new Error(await leerMensajeError(respuesta));
  return respuesta.json();
}
