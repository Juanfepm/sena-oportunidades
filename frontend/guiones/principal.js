import { actualizarEjemplos, configurarCoincidencias, pintarResumen } from "./coincidencias.js";
import { configurarAutenticacion } from "./autenticacion.js";
import { guardarPreferencias } from "./campanas.js";
import { configurarErrores, mostrarErrorProceso } from "./errores.js";
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
let proximaBusquedaGratis = null;
let intervaloDatos = null;

const datosDuranteEspera = [
  "DEBUPA es un proyecto independiente y no está afiliado al SENA.",
  "Tus preferencias ayudan a ordenar oportunidades; tú decides a quién contactar.",
  "El permiso de Gmail se solicita para enviar mensajes, sin leer tu bandeja.",
  "Contactar por correo no equivale a postularte dentro del SGVA.",
  "Puedes retirar empresas de la selección antes de confirmar un envío.",
];

function detenerDatosDuranteEspera() {
  if (intervaloDatos) window.clearInterval(intervaloDatos);
  intervaloDatos = null;
}

function iniciarDatosDuranteEspera() {
  detenerDatosDuranteEspera();
  const destino = document.querySelector("#dato-progreso");
  let indice = 0;
  destino.textContent = datosDuranteEspera[indice];
  intervaloDatos = window.setInterval(() => {
    indice = (indice + 1) % datosDuranteEspera.length;
    destino.textContent = datosDuranteEspera[indice];
  }, 2500);
}

function fechaUnMesDespues(fecha) {
  const ultimoDia = new Date(fecha.getFullYear(), fecha.getMonth() + 2, 0).getDate();
  return new Date(fecha.getFullYear(), fecha.getMonth() + 1, Math.min(fecha.getDate(), ultimoDia));
}

function textoEspera() {
  const fecha = new Intl.DateTimeFormat("es-CO", { dateStyle: "long" }).format(proximaBusquedaGratis);
  return `En el plan gratis debes esperar un mes después de una campaña con envíos. Próxima búsqueda: ${fecha}. Esta vista previa solo simula la restricción.`;
}

function configurarCookies() {
  const aviso = document.querySelector("#aviso-cookies");
  const leerPreferencia = () => {
    try { return localStorage.getItem("debupa_aviso_cookies") === "entendido"; }
    catch { return false; }
  };
  aviso.hidden = leerPreferencia();

  document.querySelector("#aceptar-cookies").addEventListener("click", () => {
    try { localStorage.setItem("debupa_aviso_cookies", "entendido"); }
    catch { /* El aviso puede cerrarse aunque el navegador bloquee el almacenamiento. */ }
    aviso.hidden = true;
  });

  document.querySelector("#restablecer-cookies").addEventListener("click", () => {
    try { localStorage.removeItem("debupa_aviso_cookies"); }
    catch { /* No se almacenó la preferencia. */ }
    aviso.hidden = false;
  });
}

function configurarFormularios() {
  const formularioCampana = document.querySelector("#formulario-campana");
  const erroresCampana = document.querySelector("#errores-campana");
  const listaExclusiones = document.querySelector("#lista-correos-excluidos");
  const agregarExclusion = document.querySelector("#agregar-correo-excluido");
  let indiceExclusion = 1;

  listaExclusiones.addEventListener("input", (evento) => {
    if (evento.target instanceof HTMLInputElement) evento.target.setCustomValidity("");
  });

  agregarExclusion.addEventListener("click", () => {
    if (listaExclusiones.children.length >= 5) return;
    indiceExclusion += 1;
    const fila = document.createElement("div");
    fila.className = "fila_exclusion";
    const campo = document.createElement("input");
    campo.id = `correo-excluido-${indiceExclusion}`;
    campo.name = `correo_excluido_${indiceExclusion}`;
    campo.type = "email";
    campo.maxLength = 254;
    campo.autocomplete = "off";
    campo.placeholder = "correo@empresa.com";
    campo.setAttribute("aria-label", `Correo de empresa excluida ${indiceExclusion}`);
    const quitar = document.createElement("button");
    quitar.className = "boton boton_secundario boton_pequeno";
    quitar.type = "button";
    quitar.textContent = "Quitar";
    quitar.setAttribute("aria-label", `Quitar correo excluido ${indiceExclusion}`);
    quitar.addEventListener("click", () => {
      fila.remove();
      agregarExclusion.disabled = false;
      document.querySelector("#correo-excluido-1").focus();
    });
    fila.append(campo, quitar);
    listaExclusiones.append(fila);
    agregarExclusion.disabled = listaExclusiones.children.length >= 5;
    campo.focus();
  });

  [["#habilidades-aprendiz", "#conteo-habilidades"], ["#actividades-deseadas", "#conteo-deseadas"],
    ["#actividades-no-deseadas", "#conteo-no-deseadas"]].forEach(([campoId, conteoId]) => {
    const campo = document.querySelector(campoId);
    const conteo = document.querySelector(conteoId);
    campo.addEventListener("input", () => { conteo.textContent = String(campo.value.length); });
  });

  activarCorreccion(formularioCampana, erroresCampana);
  formularioCampana.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const camposExclusion = [...listaExclusiones.querySelectorAll("input")];
    const vistos = new Set();
    camposExclusion.forEach((campo) => {
      campo.value = campo.value.trim().toLowerCase();
      campo.setCustomValidity(campo.value && vistos.has(campo.value) ? "este correo ya está en la lista." : "");
      if (campo.value) vistos.add(campo.value);
    });
    const correosExcluidos = [...vistos];
    if (!validarFormulario(formularioCampana, erroresCampana)) return;
    if (formularioCampana.elements.plan.value === "gratis" && proximaBusquedaGratis > new Date()) {
      erroresCampana.textContent = textoEspera();
      erroresCampana.dataset.origen = "espera";
      erroresCampana.hidden = false;
      erroresCampana.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    const boton = formularioCampana.querySelector("button[type='submit']");
    boton.disabled = true;
    const textoOriginal = boton.textContent;
    boton.textContent = "Guardando preferencias…";
    try {
      const campana = await guardarPreferencias(formularioCampana, correosExcluidos);
      formularioCampana.dataset.campanaId = campana.id;
    } catch (error) {
      erroresCampana.textContent = error instanceof Error ? error.message : "No se pudieron guardar tus preferencias.";
      erroresCampana.dataset.origen = "servidor";
      erroresCampana.hidden = false;
      erroresCampana.scrollIntoView({ block: "center", behavior: "smooth" });
      if (error?.codigo !== "navegando") {
        mostrarErrorProceso(error?.codigo, error.message);
      }
      return;
    } finally {
      boton.disabled = false;
      boton.textContent = textoOriginal;
    }
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
  const plan = document.querySelector("#plan-campana");
  const limiteArchivos = () => plan.value === "premium" ? 2 : 1;
  const actualizarArchivos = () => {
    const limite = limiteArchivos();
    entradaArchivos.multiple = limite === 2;
    document.querySelector("#ayuda-archivos").textContent = `Plan ${plan.value}: hasta ${limite} ${limite === 1 ? "archivo" : "archivos"} de 5 MB${limite === 1 ? "" : " cada uno"}. PDF, Word, texto o imagen.`;
    validarAdjuntos(entradaArchivos, erroresCorreo, listaArchivos, limite);
  };
  plan.addEventListener("change", actualizarArchivos);
  actualizarArchivos();
  activarCorreccion(formularioCorreo, erroresCorreo);
  entradaArchivos.addEventListener("change", actualizarArchivos);
  formularioCorreo.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const archivosValidos = validarAdjuntos(entradaArchivos, erroresCorreo, listaArchivos, limiteArchivos());
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
  iniciarDatosDuranteEspera();
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
    detenerDatosDuranteEspera();
    simulacionActiva = null;
    if (tipo === "envio") {
      pintarResumen(document.querySelector("#plan-campana").value);
      if (document.querySelector("#plan-campana").value === "gratis") {
        proximaBusquedaGratis = fechaUnMesDespues(new Date());
      }
    }
    irA(tipo === "busqueda" ? "confirmacion" : "resultados");
  }, 1200);
  simulacionActiva = { intervalo, tipo };
}

function configurarSimulacion() {
  document.querySelector("#iniciar-simulacion").addEventListener("click", () => iniciarSimulacion("envio"));
  document.querySelector("#cancelar-simulacion").addEventListener("click", () => {
    if (!simulacionActiva) return;
    clearInterval(simulacionActiva.intervalo);
    detenerDatosDuranteEspera();
    const destino = simulacionActiva.tipo === "busqueda" ? "correo" : "confirmacion";
    simulacionActiva = null;
    irA(destino);
  });
  window.addEventListener("hashchange", () => {
    if (simulacionActiva && window.location.hash !== "#progreso") {
      clearInterval(simulacionActiva.intervalo);
      detenerDatosDuranteEspera();
      simulacionActiva = null;
    }
  });
  document.querySelector("#crear-otra-busqueda").addEventListener("click", () => {
    const aviso = document.querySelector("#aviso-espera-gratis");
    if (document.querySelector("#plan-campana").value === "gratis" && proximaBusquedaGratis > new Date()) {
      aviso.textContent = textoEspera();
      aviso.hidden = false;
      aviso.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    aviso.hidden = true;
    irA("campana");
  });
}

if (["correo", "confirmacion", "progreso", "resultados"].includes(window.location.hash.slice(1))) {
  window.history.replaceState(null, "", "#inicio");
}

document.querySelector("#anio-actual").textContent = String(new Date().getFullYear());
configurarRutas();
configurarAutenticacion();
configurarUbicaciones();
configurarCookies();
configurarCoincidencias();
configurarErrores();
configurarFormularios();
configurarSimulacion();
