import { actualizarEjemplos, configurarCoincidencias, pintarResumen } from "./coincidencias.js";
import { configurarRutas, irA } from "./rutas.js";
import { configurarUbicaciones } from "./ubicaciones.js";
import { activarCorreccion, validarAdjuntos, validarFormulario } from "./validacion.js";

const etapas = {
  busqueda: [
    "Campaña en cola de ejemplo",
    "Turno del único navegador de ejemplo",
    "Consulta simulada de empresas",
    "Análisis ilustrativo de coincidencias",
  ],
  envio: [
    "Selección aprobada en esta demostración",
    "Comprobación ilustrativa de destinatarios",
    "Preparación simulada de mensajes",
    "Resumen de ejemplo listo",
  ],
};

let simulacionActiva = null;

function configurarCookies() {
  const aviso = document.querySelector("#aviso-cookies");
  const leerPreferencia = () => {
    try { return localStorage.getItem("rumbo_aviso_cookies") === "entendido"; }
    catch { return false; }
  };
  aviso.hidden = leerPreferencia();

  document.querySelector("#aceptar-cookies").addEventListener("click", () => {
    try { localStorage.setItem("rumbo_aviso_cookies", "entendido"); }
    catch { /* El aviso puede cerrarse aunque el navegador bloquee el almacenamiento. */ }
    aviso.hidden = true;
  });

  document.querySelector("#restablecer-cookies").addEventListener("click", () => {
    try { localStorage.removeItem("rumbo_aviso_cookies"); }
    catch { /* No se almacenó la preferencia. */ }
    aviso.hidden = false;
  });
}

function configurarFormularios() {
  const formularioCampana = document.querySelector("#formulario-campana");
  const erroresCampana = document.querySelector("#errores-campana");
  const campoExclusiones = document.querySelector("#correos-excluidos");
  const extraerExclusiones = () => campoExclusiones.value.split(/[\n,;]+/).map((correo) => correo.trim().toLowerCase()).filter(Boolean);
  campoExclusiones.addEventListener("input", () => campoExclusiones.setCustomValidity(""));
  activarCorreccion(formularioCampana, erroresCampana);
  formularioCampana.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const correosExcluidos = extraerExclusiones();
    const correoValido = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    campoExclusiones.setCustomValidity(correosExcluidos.every((correo) => correoValido.test(correo)) ? "" : "escribe direcciones válidas, separadas por línea.");
    if (!validarFormulario(formularioCampana, erroresCampana)) return;
    actualizarEjemplos({
      modalidad: formularioCampana.elements.modalidad.value,
      departamento: formularioCampana.elements.departamento.value,
      ciudad: formularioCampana.elements.ciudad.value,
      antiguedad: formularioCampana.elements.antiguedad.value,
      correosExcluidos,
    });
    irA("correo");
  });

  const formularioCorreo = document.querySelector("#formulario-correo");
  const erroresCorreo = document.querySelector("#errores-correo");
  const entradaArchivos = document.querySelector("#archivos-correo");
  const listaArchivos = document.querySelector("#lista-archivos");
  activarCorreccion(formularioCorreo, erroresCorreo);
  entradaArchivos.addEventListener("change", () => validarAdjuntos(entradaArchivos, erroresCorreo, listaArchivos));
  formularioCorreo.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const archivosValidos = validarAdjuntos(entradaArchivos, erroresCorreo, listaArchivos);
    if (!archivosValidos) return;
    if (validarFormulario(formularioCorreo, erroresCorreo)) iniciarSimulacion("busqueda");
  });
}

function actualizarProgreso(tipo, indice) {
  const barra = document.querySelector(".barra_progreso");
  const relleno = document.querySelector("#barra-progreso-relleno");
  const texto = document.querySelector("#texto-progreso");
  const lista = document.querySelector("#pasos-progreso");
  const porcentaje = Math.round(((indice + 1) / etapas[tipo].length) * 100);

  relleno.style.width = `${porcentaje}%`;
  barra.setAttribute("aria-valuenow", String(porcentaje));
  texto.textContent = `${etapas[tipo][indice]} · ${porcentaje}% de la demostración`;
  [...lista.children].forEach((paso, posicion) => {
    paso.classList.toggle("completado", posicion < indice);
    paso.classList.toggle("en_curso", posicion === indice);
  });
}

function iniciarSimulacion(tipo) {
  if (simulacionActiva) clearInterval(simulacionActiva.intervalo);
  const lista = document.querySelector("#pasos-progreso");
  lista.replaceChildren(...etapas[tipo].map((nombre) => {
    const paso = document.createElement("li");
    paso.textContent = nombre;
    return paso;
  }));

  irA("progreso");
  let indice = 0;
  actualizarProgreso(tipo, indice);
  const intervalo = window.setInterval(() => {
    indice += 1;
    if (indice < etapas[tipo].length) {
      actualizarProgreso(tipo, indice);
      return;
    }
    clearInterval(intervalo);
    simulacionActiva = null;
    if (tipo === "envio") pintarResumen();
    irA(tipo === "busqueda" ? "confirmacion" : "resultados");
  }, 1200);
  simulacionActiva = { intervalo, tipo };
}

function configurarSimulacion() {
  document.querySelector("#iniciar-simulacion").addEventListener("click", () => iniciarSimulacion("envio"));
  document.querySelector("#cancelar-simulacion").addEventListener("click", () => {
    if (!simulacionActiva) return;
    clearInterval(simulacionActiva.intervalo);
    const destino = simulacionActiva.tipo === "busqueda" ? "correo" : "confirmacion";
    simulacionActiva = null;
    irA(destino);
  });
  window.addEventListener("hashchange", () => {
    if (simulacionActiva && window.location.hash !== "#progreso") {
      clearInterval(simulacionActiva.intervalo);
      simulacionActiva = null;
    }
  });
}

document.querySelector("#anio-actual").textContent = String(new Date().getFullYear());
configurarRutas();
configurarUbicaciones();
configurarCookies();
configurarCoincidencias();
configurarFormularios();
configurarSimulacion();
