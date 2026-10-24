const ejemplos = [
  {
    id: "nexo",
    nombre: "Nexo Digital",
    inicial: "N",
    ubicacion: "Bogotá",
    departamento: "Bogotá D. C.",
    diasPublicacion: 0,
    modalidadClave: "remoto",
    correo: "ejemplo@nexo.invalid",
    telefono: "300 000 0000",
    puntaje: 88,
    modalidad: "Remoto por confirmar",
    motivo: "Sus actividades de contenido y organización digital se parecen a las que indicaste.",
  },
  {
    id: "alamo",
    nombre: "Álamo Creativo",
    inicial: "A",
    ubicacion: "Medellín",
    departamento: "Antioquia",
    diasPublicacion: 4,
    modalidadClave: "hibrido",
    correo: "ejemplo@alamo.invalid",
    telefono: "(604) 000 0000",
    puntaje: 82,
    modalidad: "Híbrido por confirmar",
    motivo: "La descripción menciona diseño y apoyo a proyectos; faltan detalles de la jornada.",
  },
  {
    id: "brisa",
    nombre: "Brisa Estudio",
    inicial: "B",
    ubicacion: "Cali",
    departamento: "Valle del Cauca",
    diasPublicacion: 13,
    modalidadClave: "presencial",
    correo: "ejemplo@brisa.invalid",
    telefono: "310 000 0000",
    puntaje: 76,
    modalidad: "Presencial",
    motivo: "El perfil solicitado comparte algunas tareas con tus intereses de práctica.",
  },
  {
    id: "savia",
    nombre: "Savia Lab",
    inicial: "S",
    ubicacion: "Bogotá",
    departamento: "Bogotá D. C.",
    diasPublicacion: 25,
    modalidadClave: "remoto",
    correo: "ejemplo@savia.invalid",
    telefono: "601 000 0000",
    puntaje: 71,
    modalidad: "Remoto por confirmar",
    motivo: "Puede encajar con tu perfil, pero la ubicación y las funciones necesitan confirmación.",
  },
];

const seleccion = new Set(ejemplos.map(({ id }) => id));
let visibles = ejemplos;

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
  document.querySelector("#iniciar-simulacion").disabled = cantidad === 0;
}

function tarjetaEmpresa(empresa) {
  const tarjeta = elemento("article", "sugerencia_tarjeta");
  const cabecera = elemento("div", "sugerencia_tarjeta_cabecera");
  const avatar = elemento("span", "avatar_empresa", empresa.inicial);
  const identidad = elemento("div");
  identidad.append(elemento("strong", "", empresa.nombre), elemento("small", "", empresa.ubicacion));
  const puntaje = elemento("span", "pildora_puntuacion", `${empresa.puntaje}% estimado`);
  cabecera.append(avatar, identidad, puntaje);
  const motivo = elemento("p", "", empresa.motivo);
  const pie = elemento("div", "sugerencia_tarjeta_pie");
  const detalle = elemento("span", "", `${empresa.modalidad} · ${empresa.correo}`);
  const boton = elemento("button", "", seleccion.has(empresa.id) ? "Quitar de la lista" : "Añadir a la lista");
  boton.type = "button";
  boton.addEventListener("click", () => alternarEmpresa(empresa.id));
  pie.append(detalle, boton);
  tarjeta.append(cabecera, motivo, pie);
  return tarjeta;
}

function elementoSeleccionado(empresa) {
  const fila = elemento("li");
  const detalle = elemento("div");
  detalle.append(elemento("strong", "", empresa.nombre), elemento("span", "", `${empresa.puntaje}% estimado · ${empresa.correo}`));
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
  listado.replaceChildren(...visibles.map(tarjetaEmpresa));
  if (visibles.length === 0) {
    listado.append(elemento("p", "estado_vacio", "No hay empresas de ejemplo para estos filtros. Ajusta la ubicación o el periodo para continuar la demostración."));
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

export function actualizarEjemplos(filtros) {
  const excluidos = new Set(filtros.correosExcluidos);
  visibles = ejemplos.filter((empresa) => {
    const modalidadCoincide = empresa.modalidadClave === filtros.modalidad;
    const departamentoCoincide = filtros.modalidad === "remoto" || filtros.departamento === "todos" || empresa.departamento === filtros.departamento;
    const ciudadCoincide = filtros.modalidad === "remoto" || filtros.ciudad === "todas" || empresa.ubicacion === filtros.ciudad;
    const periodoCoincide = empresa.diasPublicacion <= Number(filtros.antiguedad);
    return modalidadCoincide && departamentoCoincide && ciudadCoincide && periodoCoincide && !excluidos.has(empresa.correo);
  });
  seleccion.clear();
  visibles.forEach(({ id }) => seleccion.add(id));
  pintarEmpresas();
}

export function pintarResumen() {
  const tarjetas = document.querySelector("#tarjetas-resultado");
  const registro = document.querySelector("#lista-envios-resumen");
  const empresas = visibles.filter(({ id }) => seleccion.has(id));
  const fecha = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium" }).format(new Date());

  tarjetas.replaceChildren(...empresas.slice(0, 2).map((empresa) => {
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
