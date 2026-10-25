const seleccion = new Set();
let visibles = [];
let resultadosCargados = false;

function elemento(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto) nodo.textContent = texto;
  return nodo;
}

function actualizarConteo() {
  const cantidad = seleccion.size;
  document.querySelector("#conteo-seleccion").textContent = String(cantidad);
  document.querySelector("#total-seleccion").textContent = `${cantidad} ${cantidad === 1 ? "empresa" : "empresas"}`;
  document.querySelector("#iniciar-simulacion").disabled = cantidad === 0 || visibles.some(({ pendienteIa }) => pendienteIa);
}

function tarjetaEmpresa(empresa) {
  const tarjeta = elemento("article", "sugerencia_tarjeta");
  const cabecera = elemento("div", "sugerencia_tarjeta_cabecera");
  const avatar = elemento("span", "avatar_empresa", empresa.inicial);
  const identidad = elemento("div");
  identidad.append(elemento("strong", "", empresa.nombre), elemento("small", "", empresa.ubicacion));
  const puntaje = elemento("span", "pildora_puntuacion", empresa.pendienteIa ? "Sin análisis de IA" : `${empresa.puntaje}% estimado`);
  cabecera.append(avatar, identidad, puntaje);
  const motivo = elemento("p", "", empresa.motivo);
  const descripcion = elemento("details");
  if (empresa.descripcion) {
    descripcion.append(elemento("summary", "", "Ver perfil y funciones"), elemento("p", "", empresa.descripcion));
  }
  const pie = elemento("div", "sugerencia_tarjeta_pie");
  const detalle = elemento("span", "", `${empresa.modalidad} · ${empresa.correo || "Sin correo"}${empresa.pendienteIa ? ` · ${empresa.telefono}` : ""}`);
  const seleccionada = seleccion.has(empresa.id);
  const boton = elemento("button", seleccionada ? "accion_quitar" : "accion_agregar",
    seleccionada ? "Quitar de la lista" : "Añadir a la lista");
  boton.type = "button";
  boton.addEventListener("click", () => alternarEmpresa(empresa.id));
  pie.append(detalle, boton);
  tarjeta.append(cabecera, motivo);
  if (empresa.descripcion) tarjeta.append(descripcion);
  tarjeta.append(pie);
  return tarjeta;
}

function elementoSeleccionado(empresa) {
  const fila = elemento("li");
  const detalle = elemento("div");
  detalle.append(elemento("strong", "", empresa.nombre), elemento("span", "", empresa.pendienteIa ? "Pendiente de IA" : `${empresa.puntaje}% estimado · ${empresa.correo}`));
  const boton = elemento("button", "", "Quitar");
  boton.type = "button";
  boton.setAttribute("aria-label", `Quitar a ${empresa.nombre} de la lista`);
  boton.addEventListener("click", () => alternarEmpresa(empresa.id));
  fila.append(detalle, boton);
  return fila;
}

function pintarEmpresas() {
  const listado = document.querySelector("#lista-coincidencias");
  const seleccionadas = document.querySelector("#lista-seleccion");
  document.querySelector("#aviso-sin-resultados").hidden = !resultadosCargados || visibles.length > 0;
  document.querySelector(".revision_disposicion").hidden = !resultadosCargados || visibles.length === 0;
  listado.replaceChildren(...visibles.map(tarjetaEmpresa));
  if (visibles.length === 0) {
    listado.append(elemento("p", "estado_vacio", "No hay ofertas para estos filtros. Ajusta la ubicación o el periodo."));
    const enlace = elemento("a", "boton boton_secundario", "Ajustar preferencias");
    enlace.href = "#campana";
    listado.append(enlace);
  }
  seleccionadas.replaceChildren(...visibles.filter(({ id }) => seleccion.has(id)).map(elementoSeleccionado));
  if (seleccion.size === 0) seleccionadas.append(elemento("li", "", "No hay empresas seleccionadas."));
  actualizarConteo();
}

function alternarEmpresa(id) {
  if (seleccion.has(id)) seleccion.delete(id);
  else seleccion.add(id);
  pintarEmpresas();
}

export function configurarCoincidencias() {
  const panel = document.querySelector("#panel-seleccion");
  const abrir = document.querySelector("#abrir-seleccion");
  let focoAnterior = null;

  abrir.addEventListener("click", () => {
    focoAnterior = document.activeElement;
    panel.hidden = false;
    abrir.setAttribute("aria-expanded", "true");
    panel.querySelector(".boton_icono").focus();
  });

  const cerrar = () => {
    panel.hidden = true;
    abrir.setAttribute("aria-expanded", "false");
    focoAnterior?.focus();
  };
  panel.querySelectorAll("[data-cerrar-seleccion]").forEach((boton) => boton.addEventListener("click", cerrar));
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && !panel.hidden) cerrar();
    if (evento.key !== "Tab" || panel.hidden) return;
    const controles = [...panel.querySelectorAll("button:not([disabled])")];
    const primero = controles[0];
    const ultimo = controles.at(-1);
    if (evento.shiftKey && document.activeElement === primero) {
      evento.preventDefault();
      ultimo.focus();
    } else if (!evento.shiftKey && document.activeElement === ultimo) {
      evento.preventDefault();
      primero.focus();
    }
  });
  pintarEmpresas();
}

export function cargarCoincidencias(destinatarios, campana) {
  const modalidades = { remoto: "Remoto por confirmar", hibrido: "Híbrido por confirmar", presencial: "Presencial por confirmar" };
  visibles = destinatarios.map((destinatario) => ({
    id: destinatario.id,
    nombre: destinatario.nombre_empresa,
    inicial: destinatario.nombre_empresa.charAt(0),
    ubicacion: destinatario.departamento ? `${destinatario.ciudad || ""}, ${destinatario.departamento}` : "Oferta ficticia",
    correo: destinatario.correo,
    telefono: destinatario.telefono_original || "Sin número",
    descripcion: destinatario.descripcion,
    puntaje: destinatario.puntuacion,
    pendienteIa: destinatario.estado === "pendiente_ia",
    modalidad: modalidades[campana.modalidad],
    motivo: destinatario.motivo,
  }));
  resultadosCargados = true;
  seleccion.clear();
  visibles.filter(({ puntaje, pendienteIa }) => !pendienteIa && puntaje >= 80).forEach(({ id }) => seleccion.add(id));
  document.querySelector("#iniciar-simulacion").hidden = campana.modo_consulta === "sgva";
  document.querySelector("#aviso-sin-resultados strong").textContent = campana.modo_consulta === "sgva"
    ? "No encontramos solicitudes recientes con estos filtros."
    : "No encontramos coincidencias suficientemente buenas con estos filtros.";
  document.querySelector("#confirmacion .pagina_encabezado p").textContent = campana.modo_consulta === "sgva"
    ? "Estas ofertas se consultaron en SGVA. Todavía no tienen análisis de IA y no se enviará ningún correo a empresas."
    : "Estas empresas y porcentajes son ficticios. El perfil que redactaste todavía no interviene en la puntuación; la modalidad requiere confirmación con la empresa.";
  document.querySelector("#confirmacion .resumen_revision > p").textContent = campana.modo_consulta === "sgva"
    ? "Puedes revisar contactos y descripciones. La clasificación y el envío se habilitarán en próximas etapas."
    : "Revisaremos los destinatarios excluidos y los contactos recientes. La versión operativa solicitará una confirmación final antes de enviar.";
  pintarEmpresas();
}

export function pintarResumen(plan) {
  const tarjetas = document.querySelector("#tarjetas-resultado");
  const registro = document.querySelector("#lista-envios-resumen");
  const empresas = visibles.filter(({ id }) => seleccion.has(id));
  const fecha = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium" }).format(new Date());

  tarjetas.replaceChildren(...empresas.slice(0, plan === "premium" ? 30 : 2).map((empresa) => {
    const tarjeta = elemento("article", "resultado_tarjeta");
    const cabecera = elemento("div", "resultado_tarjeta_cabecera");
    cabecera.append(elemento("span", "avatar_empresa", empresa.inicial), elemento("span", "pildora_puntuacion", `${empresa.puntaje}% estimado`));
    const detalles = elemento("dl");
    [["Correo", empresa.correo], ["Contacto", empresa.telefono], ["Estado", "Demostración, no enviado"], ["Fecha", fecha]].forEach(([clave, valor]) => {
      const fila = elemento("div");
      fila.append(elemento("dt", "", clave), elemento("dd", "", valor));
      detalles.append(fila);
    });
    tarjeta.append(cabecera, elemento("h2", "", empresa.nombre), elemento("p", "", empresa.motivo), detalles);
    return tarjeta;
  }));

  registro.replaceChildren(...empresas.map((empresa) => {
    const fila = elemento("li");
    fila.append(elemento("strong", "", empresa.nombre), elemento("span", "", `${empresa.correo} · no enviado`));
    return fila;
  }));
}
