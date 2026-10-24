const departamentos = [
  ["Amazonas", ["Leticia", "Puerto Nariño"]],
  ["Antioquia", ["Medellín", "Bello", "Envigado", "Itagüí", "Rionegro"]],
  ["Arauca", ["Arauca", "Saravena", "Tame"]],
  ["Atlántico", ["Barranquilla", "Soledad", "Malambo"]],
  ["Bogotá D. C.", ["Bogotá"]],
  ["Bolívar", ["Cartagena", "Magangué", "Turbaco"]],
  ["Boyacá", ["Tunja", "Duitama", "Sogamoso"]],
  ["Caldas", ["Manizales", "La Dorada", "Chinchiná"]],
  ["Caquetá", ["Florencia", "San Vicente del Caguán"]],
  ["Casanare", ["Yopal", "Aguazul", "Villanueva"]],
  ["Cauca", ["Popayán", "Santander de Quilichao"]],
  ["Cesar", ["Valledupar", "Aguachica"]],
  ["Chocó", ["Quibdó", "Istmina"]],
  ["Córdoba", ["Montería", "Cereté", "Lorica"]],
  ["Cundinamarca", ["Soacha", "Chía", "Facatativá", "Zipaquirá"]],
  ["Guainía", ["Inírida"]],
  ["Guaviare", ["San José del Guaviare"]],
  ["Huila", ["Neiva", "Pitalito", "Garzón"]],
  ["La Guajira", ["Riohacha", "Maicao", "Uribia"]],
  ["Magdalena", ["Santa Marta", "Ciénaga"]],
  ["Meta", ["Villavicencio", "Acacías", "Granada"]],
  ["Nariño", ["Pasto", "Ipiales", "Tumaco"]],
  ["Norte de Santander", ["Cúcuta", "Ocaña", "Villa del Rosario"]],
  ["Putumayo", ["Mocoa", "Puerto Asís"]],
  ["Quindío", ["Armenia", "Calarcá", "Montenegro"]],
  ["Risaralda", ["Pereira", "Dosquebradas", "Santa Rosa de Cabal"]],
  ["San Andrés y Providencia", ["San Andrés", "Providencia"]],
  ["Santander", ["Bucaramanga", "Floridablanca", "Barrancabermeja"]],
  ["Sucre", ["Sincelejo", "Corozal"]],
  ["Tolima", ["Ibagué", "Espinal", "Melgar"]],
  ["Valle del Cauca", ["Cali", "Palmira", "Buenaventura", "Tuluá"]],
  ["Vaupés", ["Mitú"]],
  ["Vichada", ["Puerto Carreño"]],
];

function agregarOpcion(selector, valor, etiqueta) {
  const opcion = document.createElement("option");
  opcion.value = valor;
  opcion.textContent = etiqueta;
  selector.append(opcion);
}

export function configurarUbicaciones() {
  const modalidad = document.querySelector("#modalidad-trabajo");
  const departamento = document.querySelector("#departamento-busqueda");
  const ciudad = document.querySelector("#ciudad-busqueda");

  departamentos.forEach(([nombre]) => agregarOpcion(departamento, nombre, nombre));

  function actualizarCiudades() {
    ciudad.replaceChildren();
    agregarOpcion(ciudad, "todas", "Todas las ciudades");
    const ciudades = departamentos.find(([nombre]) => nombre === departamento.value)?.[1] ?? [];
    ciudades.forEach((nombre) => agregarOpcion(ciudad, nombre, nombre));
    ciudad.disabled = modalidad.value === "remoto" || ciudades.length === 0;
  }

  function actualizarModalidad() {
    const esRemoto = modalidad.value === "remoto";
    departamento.disabled = esRemoto;
    if (esRemoto) departamento.value = "todos";
    if (!esRemoto && departamento.value === "todos") departamento.value = "";
    actualizarCiudades();
  }

  departamento.addEventListener("change", actualizarCiudades);
  modalidad.addEventListener("change", actualizarModalidad);
  actualizarModalidad();
}
