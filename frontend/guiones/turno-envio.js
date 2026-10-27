import { liberarTurnoConfirmacion, solicitarTurnoConfirmacion } from "./campanas.js";

const botonEscritorio = document.querySelector("#iniciar-simulacion");
const botonMovil = document.querySelector("#iniciar-envio-movil");
const indicadores = [document.querySelector("#espera-envio-escritorio"), document.querySelector("#espera-envio-movil")];
const panelEspera = document.querySelector("#panel-espera-envio");

export function crearTurnoEnvio(obtenerCampana, abrirConfirmacion, mostrarError) {
  let campanaId = null;
  let version = 0;
  let temporizador = null;
  let latido = null;
  let ocupado = false;
  let focoAnterior = null;

  const indicar = (mensaje) => {
    for (const indicador of indicadores) {
      indicador.hidden = !mensaje;
      indicador.querySelector("span").textContent = mensaje;
    }
  };

  const limpiarVista = () => {
    window.clearTimeout(temporizador);
    window.clearInterval(latido);
    panelEspera.hidden = true;
    indicar(null);
    const haySeleccion = Number(document.querySelector("#conteo-seleccion").textContent) > 0;
    botonEscritorio.disabled = !haySeleccion;
    botonMovil.disabled = !haySeleccion;
    ocupado = false;
  };

  const liberar = async () => {
    version += 1;
    const anterior = campanaId;
    campanaId = null;
    limpiarVista();
    focoAnterior?.focus();
    if (anterior) await liberarTurnoConfirmacion(anterior).catch(() => {});
  };

  const consultar = async (actual) => {
    const idConsultado = campanaId;
    try {
      const turno = await solicitarTurnoConfirmacion(idConsultado);
      if (actual !== version) {
        await liberarTurnoConfirmacion(idConsultado).catch(() => {});
        return;
      }
      if (turno.estado === "en_espera") {
        if (panelEspera.hidden) {
          panelEspera.hidden = false;
          document.querySelector("#cancelar-espera-envio").focus();
        }
        const delante = turno.personas_delante;
        const mensaje = delante === 1 ? "Hay 1 persona antes que tú." : `Hay ${delante} personas antes que tú.`;
        document.querySelector("#detalle-espera-envio").textContent = `${mensaje} Tu revisión se abrirá automáticamente.`;
        indicar("Esperando turno para confirmar el envío…");
        temporizador = window.setTimeout(() => consultar(actual), 2000);
        return;
      }
      panelEspera.hidden = true;
      indicar("Preparando la revisión final…");
      await abrirConfirmacion(idConsultado, () => actual === version, focoAnterior);
      if (actual !== version) return;
      indicar(null);
      latido = window.setInterval(async () => {
        try {
          const renovacion = await solicitarTurnoConfirmacion(idConsultado);
          if (actual !== version) {
            await liberarTurnoConfirmacion(idConsultado).catch(() => {});
            return;
          }
          if (renovacion.estado !== "listo") throw new Error("Tu turno de revisión venció. Vuelve a abrir la lista.");
        } catch (error) {
          if (actual !== version) return;
          await liberar();
          mostrarError(error);
        }
      }, 20000);
    } catch (error) {
      if (actual !== version) return;
      await liberar();
      mostrarError(error);
    }
  };

  const iniciar = async () => {
    if (ocupado) return;
    focoAnterior = document.activeElement;
    ocupado = true;
    botonEscritorio.disabled = true;
    botonMovil.disabled = true;
    indicar("Preparando tu turno…");
    const actual = ++version;
    try {
      campanaId = await obtenerCampana();
      if (actual !== version) return;
      await consultar(actual);
    } catch (error) {
      if (actual !== version) return;
      await liberar();
      mostrarError(error);
    }
  };

  document.querySelector("#cancelar-espera-envio").addEventListener("click", () => { void liberar(); });
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && !panelEspera.hidden) void liberar();
  });
  window.addEventListener("hashchange", () => {
    if (campanaId && window.location.hash !== "#confirmacion") void liberar();
  });
  window.addEventListener("pagehide", () => {
    if (campanaId) void liberarTurnoConfirmacion(campanaId, true).catch(() => {});
  });

  return {
    iniciar,
    liberar,
    completado: () => { version += 1; campanaId = null; limpiarVista(); },
  };
}
