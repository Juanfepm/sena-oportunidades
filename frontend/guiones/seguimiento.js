import { consultarCampana, consultarDestinatarios, listarCampanas } from "./campanas.js";
import { cargarCoincidencias } from "./coincidencias.js";
import { mostrarErrorProceso } from "./errores.js";
import { irA } from "./rutas.js";

const etapas = ["En cola para la demostración", "Validando preferencias", "Preparando ofertas ficticias", "Resultados disponibles"];
const datos = [
  "DEBUPA es independiente y no está afiliado al SENA.",
  "El permiso de Gmail no permite leer tu bandeja.",
  "Contactar por correo no equivale a postularte dentro de SGVA.",
  "Puedes retirar empresas de la selección antes de confirmar.",
];
let seguimiento = null;
let intervaloDatos = null;
let campañaReanudable = null;

export function detenerDatosDuranteEspera() {
  if (intervaloDatos) window.clearInterval(intervaloDatos);
  intervaloDatos = null;
}

export function iniciarDatosDuranteEspera() {
  detenerDatosDuranteEspera();
  const destino = document.querySelector("#dato-progreso");
  let indice = 0;
  destino.textContent = datos[indice];
  intervaloDatos = window.setInterval(() => {
    indice = (indice + 1) % datos.length;
    destino.textContent = datos[indice];
  }, 2500);
}

export function detenerSeguimiento() {
  if (seguimiento?.temporizador) window.clearTimeout(seguimiento.temporizador);
  seguimiento = null;
  detenerDatosDuranteEspera();
}

export function haySeguimiento() {
  return seguimiento !== null;
}

function pintarEstado(campana) {
  const porcentaje = Math.max(0, Math.min(100, campana.progreso));
  document.querySelector("#barra-progreso-relleno").style.width = `${porcentaje}%`;
  document.querySelector(".barra_progreso").setAttribute("aria-valuenow", String(porcentaje));
  document.querySelector("#texto-progreso").textContent = `${campana.etapa} · ${porcentaje}%`;
  const indice = campana.estado === "en_cola" ? 0 : porcentaje < 40 ? 1 : porcentaje < 100 ? 2 : 3;
  [...document.querySelector("#pasos-progreso").children].forEach((paso, posicion) => {
    paso.classList.toggle("completado", posicion < indice);
    paso.classList.toggle("en_curso", posicion === indice);
  });
}

async function abrirResultados(campana, referencia) {
  const destinatarios = await consultarDestinatarios(campana.id);
  if (referencia && seguimiento !== referencia) return;
  cargarCoincidencias(destinatarios, campana);
  campañaReanudable = campana;
  document.querySelector("#texto-reanudar-campana").textContent = "Tus ofertas ficticias están listas para revisar.";
  document.querySelector("#boton-reanudar-campana").textContent = "Ver resultados de ejemplo";
  detenerSeguimiento();
  irA("confirmacion");
}

async function revisar(referencia) {
  try {
    const campana = await consultarCampana(referencia.id);
    if (seguimiento !== referencia) return;
    pintarEstado(campana);
    if (campana.estado === "esperando_confirmacion") {
      await abrirResultados(campana, referencia);
      return;
    }
    if (["error", "cancelada", "interrumpida"].includes(campana.estado)) {
      detenerSeguimiento();
      mostrarErrorProceso("servicio", campana.etapa);
      return;
    }
  } catch (error) {
    if (seguimiento !== referencia) return;
    document.querySelector("#texto-progreso").textContent = "No pudimos actualizar el progreso. Volveremos a intentar.";
  }
  if (seguimiento === referencia) referencia.temporizador = window.setTimeout(() => revisar(referencia), 1200);
}

export function iniciarSeguimiento(campanaId) {
  detenerSeguimiento();
  campañaReanudable = { id: campanaId, estado: "en_cola" };
  document.querySelector("#texto-reanudar-campana").textContent = "Tu campaña de ejemplo sigue en curso en el servidor.";
  document.querySelector("#boton-reanudar-campana").textContent = "Ver progreso";
  document.querySelector("#reanudar-campana").hidden = false;
  document.querySelector("#pasos-progreso").replaceChildren(...etapas.map((etapa) => {
    const paso = document.createElement("li");
    paso.textContent = etapa;
    return paso;
  }));
  document.querySelector("#cancelar-simulacion").textContent = "Volver al inicio";
  document.querySelector("#texto-progreso").textContent = "Consultando el estado de tu campaña…";
  document.querySelector("#barra-progreso-relleno").style.width = "0%";
  document.querySelector(".barra_progreso").setAttribute("aria-valuenow", "0");
  iniciarDatosDuranteEspera();
  seguimiento = { id: campanaId, temporizador: null };
  irA("progreso");
  revisar(seguimiento);
}

export function configurarSeguimiento() {
  const panel = document.querySelector("#reanudar-campana");
  let versionCuenta = 0;
  document.querySelector("#boton-reanudar-campana").addEventListener("click", async () => {
    if (!campañaReanudable) return;
    const campana = campañaReanudable;
    if (campana.estado === "esperando_confirmacion") {
      try { await abrirResultados(campana); }
      catch (error) { mostrarErrorProceso("servicio", error.message); }
    } else iniciarSeguimiento(campana.id);
  });
  window.addEventListener("debupa:cuenta-actualizada", async (evento) => {
    const version = ++versionCuenta;
    campañaReanudable = null;
    panel.hidden = true;
    if (!evento.detail) {
      detenerSeguimiento();
      return;
    }
    try {
      const campanas = await listarCampanas();
      if (version !== versionCuenta || !Array.isArray(campanas)) return;
      campañaReanudable = campanas.find(({ estado }) => ["en_cola", "consultando", "esperando_confirmacion"].includes(estado));
      if (!campañaReanudable) return;
      const lista = campañaReanudable.estado === "esperando_confirmacion";
      document.querySelector("#texto-reanudar-campana").textContent = lista
        ? "Tienes ofertas ficticias listas para revisar." : "Tu campaña de ejemplo sigue en curso en el servidor.";
      document.querySelector("#boton-reanudar-campana").textContent = lista
        ? "Ver resultados de ejemplo" : "Ver progreso";
      panel.hidden = false;
    } catch {
      panel.hidden = true;
    }
  });
  window.addEventListener("hashchange", () => {
    if (seguimiento && window.location.hash !== "#progreso") detenerSeguimiento();
  });
}
