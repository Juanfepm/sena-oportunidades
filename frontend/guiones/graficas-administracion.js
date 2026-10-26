const espacioSvg = "http://www.w3.org/2000/svg";

function elementoSvg(nombre, atributos = {}) {
  const elemento = document.createElementNS(espacioSvg, nombre);
  for (const [clave, valor] of Object.entries(atributos)) elemento.setAttribute(clave, String(valor));
  return elemento;
}

export function mensajeVacio(texto, claro = false) {
  const contenedor = document.createElement("p");
  contenedor.className = claro ? "admin_vacio admin_vacio_claro" : "admin_vacio";
  const icono = elementoSvg("svg", { class: "icono", "aria-hidden": "true" });
  icono.append(elementoSvg("use", { href: "./recursos/iconos.svg#informacion" }));
  contenedor.append(icono, document.createTextNode(texto));
  return contenedor;
}

function pintarDistribucion(gratis, premium) {
  const destino = document.querySelector("#admin-grafica-planes");
  const total = gratis + premium;
  if (!total) { destino.replaceChildren(mensajeVacio("Aún no hay cuentas registradas.")); return; }
  const grafica = elementoSvg("svg", { viewBox: "0 0 200 200", role: "img", "aria-label": `${gratis} usuarios gratis y ${premium} usuarios Premium` });
  const radio = 66;
  const circunferencia = 2 * Math.PI * radio;
  const base = { cx: 100, cy: 100, r: radio, fill: "none", "stroke-width": 24, transform: "rotate(-90 100 100)" };
  grafica.append(elementoSvg("circle", { ...base, stroke: "#a9c8d2" }));
  if (premium) grafica.append(elementoSvg("circle", {
    ...base, stroke: "#83d7a6", "stroke-dasharray": `${circunferencia * premium / total} ${circunferencia}`,
    "stroke-linecap": "round",
  }));
  const cifra = elementoSvg("text", { x: 100, y: 99, fill: "#fff", "font-size": 30, "font-weight": 800, "text-anchor": "middle" });
  cifra.textContent = String(total);
  const etiqueta = elementoSvg("text", { x: 100, y: 119, fill: "#c5dad0", "font-size": 12, "text-anchor": "middle" });
  etiqueta.textContent = "usuarios";
  grafica.append(cifra, etiqueta);
  destino.replaceChildren(grafica);
}

function pintarEvolucion(meses) {
  const destino = document.querySelector("#admin-grafica-evolucion");
  if (!meses.some((mes) => mes.postuladas || mes.aprobadas || mes.rechazadas)) {
    destino.replaceChildren(mensajeVacio("Aún no hay solicitudes en los últimos seis meses."));
    return;
  }
  const grafica = elementoSvg("svg", { viewBox: "0 0 440 205", role: "img", "aria-label": "Evolución mensual de solicitudes Premium postuladas, aceptadas y rechazadas" });
  const maximo = Math.max(1, ...meses.flatMap((mes) => [mes.postuladas, mes.aprobadas, mes.rechazadas]));
  const x = (indice) => 35 + indice * 76;
  const y = (valor) => 160 - valor / maximo * 120;
  for (let fila = 0; fila < 3; fila += 1) {
    grafica.append(elementoSvg("line", { x1: 30, x2: 420, y1: 40 + fila * 60, y2: 40 + fila * 60, stroke: "#66847a", "stroke-opacity": 0.45 }));
  }
  const series = [
    ["postuladas", "#c5b3f5"], ["aprobadas", "#83d7a6"], ["rechazadas", "#ffb1a4"],
  ];
  for (const [clave, color] of series) {
    const puntos = meses.map((mes, indice) => `${x(indice)},${y(mes[clave])}`).join(" ");
    grafica.append(elementoSvg("polyline", { points: puntos, fill: "none", stroke: color, "stroke-width": 3, "stroke-linecap": "round", "stroke-linejoin": "round" }));
    meses.forEach((mes, indice) => grafica.append(elementoSvg("circle", { cx: x(indice), cy: y(mes[clave]), r: 3.5, fill: color })));
  }
  meses.forEach((mes, indice) => {
    const etiqueta = elementoSvg("text", { x: x(indice), y: 190, fill: "#c5dad0", "font-size": 11, "text-anchor": "middle" });
    etiqueta.textContent = new Intl.DateTimeFormat("es-CO", { month: "short" }).format(new Date(`${mes.mes}-01T12:00:00`));
    grafica.append(etiqueta);
  });
  destino.replaceChildren(grafica);
}

export function pintarGraficas(datos) {
  pintarDistribucion(Number(datos.gratis) || 0, Number(datos.premium) || 0);
  pintarEvolucion(datos.evolucion_premium || []);
}
