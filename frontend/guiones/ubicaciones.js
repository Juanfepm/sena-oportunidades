function agregarOpcion(selector, valor, etiqueta) {
  const opcion = document.createElement("option");
  opcion.value = valor;
  opcion.textContent = etiqueta;
  selector.append(opcion);
}

export async function configurarUbicaciones() {
  const modalidad = document.querySelector("#modalidad-trabajo");
  const departamento = document.querySelector("#departamento-busqueda");
  const municipio = document.querySelector("#ciudad-busqueda");
  departamento.disabled = true;
  municipio.disabled = true;

  try {
    const respuesta = await fetch(new URL("../datos/municipios.json", import.meta.url));
    if (!respuesta.ok) throw new Error("No se pudo descargar el catálogo local.");
    const { departamentos } = await respuesta.json();
    Object.keys(departamentos).forEach((nombre) => agregarOpcion(departamento, nombre, nombre));

    function actualizarMunicipios() {
      municipio.replaceChildren();
      agregarOpcion(municipio, "todas", "Todos los municipios");
      const nombres = departamentos[departamento.value] ?? [];
      nombres.forEach((nombre) => agregarOpcion(municipio, nombre, nombre));
      municipio.disabled = modalidad.value === "remoto" || nombres.length === 0;
    }

    function actualizarModalidad() {
      const esRemoto = modalidad.value === "remoto";
      departamento.disabled = esRemoto || !modalidad.value;
      if (esRemoto) departamento.value = "todos";
      actualizarMunicipios();
    }

    departamento.addEventListener("change", actualizarMunicipios);
    modalidad.addEventListener("change", actualizarModalidad);
    actualizarModalidad();
  } catch {
    const aviso = document.querySelector("#errores-campana");
    aviso.textContent = "No se pudieron cargar los municipios. Actualiza la página para intentarlo de nuevo.";
    aviso.hidden = false;
    document.querySelector("#formulario-campana button[type='submit']").disabled = true;
  }
}
