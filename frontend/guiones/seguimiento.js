import { consultarCampana, consultarDestinatarios, consultarResultadoEnvio, consultarTurno, listarCampanas } from "./campanas.js";
import { cargarCoincidencias, pintarResultadoEnvio } from "./coincidencias.js";
import { mostrarErrorProceso } from "./errores.js";
import { irA } from "./rutas.js";

const etapas = ["En cola para la consulta", "Accediendo al servicio", "Revisando solicitudes", "Resultados disponibles"];
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

export function campanaEnSeguimiento() {
  return seguimiento && { id: seguimiento.id, tipo: seguimiento.tipo };
}

function pintarEstado(campana, referencia) {
  const recibido = Math.max(0, Math.min(100, Number(campana.progreso) || 0));
  referencia.maximoMostrado = Math.max(referencia.maximoMostrado, recibido);
  const porcentaje = referencia.maximoMostrado;
  document.querySelector("#barra-progreso-relleno").style.width = `${porcentaje}%`;
  document.querySelector(".barra_progreso").setAttribute("aria-valuenow", String(porcentaje));
  const prefijoError = "SGVA rechazó la consulta:";
  const rechazo = campana.etapa.startsWith(prefijoError);
  const motivo = document.querySelector("#motivo-progreso");
  document.querySelector("#texto-progreso").textContent = `${rechazo ? "SGVA rechazó la consulta" : campana.etapa} · ${porcentaje}%`;
  motivo.textContent = rechazo ? `Posible motivo: ${campana.etapa.slice(prefijoError.length).trim()}` : "";
  motivo.hidden = !rechazo;
  const indice = campana.estado === "en_cola" ? 0 : porcentaje < 40 ? 1 : porcentaje < 100 ? 2 : 3;
  [...document.querySelector("#pasos-progreso").children].forEach((paso, posicion) => {
    paso.classList.toggle("completado", posicion < indice);
    paso.classList.toggle("en_curso", posicion === indice);
  });
}

async function abrirResultados(campana, referencia) {
  const actual = referencia ? campana : await consultarCampana(campana.id);
  const { destinatarios, resultadosOcultos, planActual, limiteContactos } = await consultarDestinatarios(actual.id);
  if (referencia && seguimiento !== referencia) return;
  cargarCoincidencias(destinatarios, {
    ...actual, plan_aplicado: planActual || actual.plan_aplicado,
    limite_contactos: limiteContactos,
  }, resultadosOcultos);
  campañaReanudable = actual;
  document.querySelector("#texto-reanudar-campana").textContent = actual.modo_consulta === "sgva" ? "Tus ofertas de SGVA están listas para revisar." : "Tus ofertas ficticias están listas para revisar.";
  document.querySelector("#boton-reanudar-campana").textContent = actual.modo_consulta === "sgva" ? "Ver ofertas consultadas" : "Ver resultados de ejemplo";
  detenerSeguimiento();
  irA("confirmacion");
}

async function abrirResultadoEnvio(campana, referencia) {
  const resultados = await consultarResultadoEnvio(campana.id);
  if (referencia && seguimiento !== referencia) return;
  pintarResultadoEnvio(resultados, campana.plan_aplicado, campana);
  campañaReanudable = campana;
  document.querySelector("#texto-reanudar-campana").textContent = "Consulta el resultado de tu envío.";
  document.querySelector("#boton-reanudar-campana").textContent = "Ver resultado del envío";
  detenerSeguimiento();
  irA("resultados");
}

async function revisar(referencia) {
  try {
    const campana = await consultarCampana(referencia.id);
    if (seguimiento !== referencia) return;
    pintarEstado(campana, referencia);
    if (campana.estado === "en_cola" && referencia.tipo === "consulta") {
      const turno = await consultarTurno(referencia.id);
      if (seguimiento !== referencia) return;
      const delante = turno.personas_delante;
      document.querySelector("#estado-turno").textContent = delante > 0
        ? `${delante} ${delante === 1 ? "campaña antes de la tuya" : "campañas antes de la tuya"}. Te avisaremos cuando empiece la consulta.`
        : "Tu búsqueda es la siguiente. Estamos preparando el navegador.";
      if (window.location.hash !== "#espera") irA("espera");
    } else if (window.location.hash === "#espera") {
      irA("progreso");
    }
    if (campana.estado === "esperando_confirmacion") {
      await abrirResultados(campana, referencia);
      return;
    }
    if (referencia.tipo === "envio" && ["completada", "interrumpida", "error"].includes(campana.estado)) {
      await abrirResultadoEnvio(campana, referencia);
      return;
    }
    if (["error", "cancelada", "interrumpida"].includes(campana.estado)) {
      detenerSeguimiento();
      campañaReanudable = null;
      document.querySelector("#reanudar-campana").hidden = true;
      const rechazo = campana.etapa.startsWith("SGVA rechazó la consulta:");
      const credenciales = rechazo && /usuario|contraseña|documento/i.test(campana.etapa);
      mostrarErrorProceso(credenciales ? "sgva_credenciales" : rechazo ? "sgva_restringido" : "servicio",
        rechazo ? `SGVA informó: ${campana.etapa.split(":").slice(1).join(":").trim()} Revisa tus datos y vuelve a intentarlo.` : campana.etapa,
        referencia.tipo === "consulta" ? "campana" : null);
      return;
    }
  } catch (error) {
    if (seguimiento !== referencia) return;
    document.querySelector("#texto-progreso").textContent = "No pudimos actualizar el progreso. Volveremos a intentar.";
  }
  if (seguimiento === referencia) referencia.temporizador = window.setTimeout(() => revisar(referencia), 1200);
}

export function iniciarSeguimiento(campanaId, tipo = "consulta") {
  detenerSeguimiento();
  campañaReanudable = { id: campanaId, estado: "en_cola" };
  document.querySelector("#texto-reanudar-campana").textContent = tipo === "envio" ? "Gmail está procesando tus mensajes." : "Tu consulta sigue en curso en el servidor.";
  document.querySelector("#boton-reanudar-campana").textContent = "Ver progreso";
  document.querySelector("#reanudar-campana").hidden = false;
  document.querySelector("#progreso .progreso_principal .ceja").textContent = tipo === "envio" ? "Envío por Gmail" : "Consulta de SGVA";
  document.querySelector("#progreso h1").textContent = tipo === "envio"
    ? "Enviando tus mensajes autorizados." : "Buscando ofertas visibles para ti.";
  document.querySelector("#progreso .panel_ayuda_progreso p").textContent = tipo === "envio"
    ? "Puedes cerrar el navegador. El servidor continuará mientras siga encendido y conservará el resultado." : "Las consultas esperan su turno y su estado queda disponible mientras el servidor siga activo.";
  document.querySelector("#progreso .nota_fina").textContent = tipo === "envio"
    ? "Cancelar detiene los mensajes pendientes; los ya enviados no se pueden retirar. Si Gmail no confirma uno, revisa Enviados." : "Se lee SGVA sin postularte ni enviar correos durante la consulta.";
  const nombresEtapas = tipo === "envio" ? ["En cola para enviar", "Preparando los mensajes", "Enviando uno a uno", "Resultado disponible"] : etapas;
  document.querySelector("#pasos-progreso").replaceChildren(...nombresEtapas.map((etapa) => {
    const paso = document.createElement("li");
    paso.textContent = etapa;
    return paso;
  }));
  document.querySelector("#cancelar-simulacion").textContent = "Cancelar proceso";
  document.querySelector("#motivo-progreso").hidden = true;
  document.querySelector("#texto-progreso").textContent = "Consultando el estado de tu campaña…";
  document.querySelector("#barra-progreso-relleno").style.width = "0%";
  document.querySelector(".barra_progreso").setAttribute("aria-valuenow", "0");
  iniciarDatosDuranteEspera();
  seguimiento = { id: campanaId, tipo, temporizador: null, maximoMostrado: 0 };
  irA(tipo === "consulta" ? "espera" : "progreso");
  revisar(seguimiento);
}

export function configurarSeguimiento() {
  const panel = document.querySelector("#reanudar-campana");
  let versionCuenta = 0;
  document.querySelector("#boton-reanudar-campana").addEventListener("click", async () => {
    if (!campañaReanudable) return;
    const campana = campañaReanudable;
    if (["completada", "interrumpida", "error"].includes(campana.estado) && campana.modo_consulta === "sgva" && campana.seleccion_guardada) {
      try { await abrirResultadoEnvio(campana); }
      catch (error) { mostrarErrorProceso("servicio", error.message); }
    } else if (campana.estado === "esperando_confirmacion") {
      try { await abrirResultados(campana); }
      catch (error) { mostrarErrorProceso("servicio", error.message); }
    } else iniciarSeguimiento(campana.id, campana.estado === "enviando" ? "envio" : "consulta");
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
      campañaReanudable = campanas.find(({ estado, modo_consulta, seleccion_guardada }) =>
        ["en_cola", "consultando", "esperando_confirmacion", "enviando"].includes(estado)
        || (modo_consulta === "sgva" && seleccion_guardada && ["completada", "interrumpida", "error"].includes(estado)));
      if (!campañaReanudable) return;
      const lista = campañaReanudable.estado === "esperando_confirmacion";
      const resultadoEnvio = ["completada", "interrumpida", "error"].includes(campañaReanudable.estado)
        && campañaReanudable.modo_consulta === "sgva" && campañaReanudable.seleccion_guardada;
      document.querySelector("#texto-reanudar-campana").textContent = lista
        ? (campañaReanudable.modo_consulta === "sgva" ? "Tienes ofertas de SGVA listas para revisar." : "Tienes ofertas ficticias listas para revisar.")
        : resultadoEnvio ? "Consulta el resultado de tu envío." : "Tu campaña sigue en curso en el servidor.";
      document.querySelector("#boton-reanudar-campana").textContent = lista
        ? (campañaReanudable.modo_consulta === "sgva" ? "Ver ofertas consultadas" : "Ver resultados de ejemplo")
        : resultadoEnvio ? "Ver resultado del envío" : "Ver progreso";
      panel.hidden = false;
    } catch {
      panel.hidden = true;
    }
  });
  window.addEventListener("hashchange", () => {
    if (seguimiento && !["#progreso", "#espera"].includes(window.location.hash)) detenerSeguimiento();
  });
}
