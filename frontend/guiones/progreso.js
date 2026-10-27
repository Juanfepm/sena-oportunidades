import { asegurarSeleccionGuardada, pintarResumen } from "./coincidencias.js";
import { cancelarCampana, confirmarEnvio, prepararEnvio } from "./campanas.js";
import { mostrarErrorProceso } from "./errores.js";
import { irA } from "./rutas.js";
import { campanaEnSeguimiento, detenerDatosDuranteEspera, detenerSeguimiento, iniciarDatosDuranteEspera, iniciarSeguimiento } from "./seguimiento.js";
import { crearTurnoEnvio } from "./turno-envio.js";
import { estadoAplicacion } from "./estado-aplicacion.js";

const etapas = {
  envio: [
    "Selección aprobada en esta demostración",
    "Comprobación ilustrativa de destinatarios",
    "Preparación simulada de mensajes",
    "Resumen de ejemplo listo",
  ],
};

export function fechaUnMesDespues(fecha) {
  const ultimoDia = new Date(fecha.getFullYear(), fecha.getMonth() + 2, 0).getDate();
  return new Date(fecha.getFullYear(), fecha.getMonth() + 1, Math.min(fecha.getDate(), ultimoDia));
}

export function textoEspera() {
  const fecha = new Intl.DateTimeFormat("es-CO", { dateStyle: "long" }).format(estadoAplicacion.proximaBusquedaGratis);
  return `En el plan gratis debes esperar un mes después de una campaña con envíos. Próxima búsqueda: ${fecha}. Esta vista previa solo simula la restricción.`;
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
  if (estadoAplicacion.simulacionActiva) clearInterval(estadoAplicacion.simulacionActiva.intervalo);
  iniciarDatosDuranteEspera();
  document.querySelector("#motivo-progreso").hidden = true;
  document.querySelector("#cancelar-simulacion").textContent = "Detener ejemplo";
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
    estadoAplicacion.simulacionActiva = null;
    pintarResumen(document.querySelector("#plan-campana").value);
    if (document.querySelector("#plan-campana").value === "gratis") {
      estadoAplicacion.proximaBusquedaGratis = fechaUnMesDespues(new Date());
    }
    irA("resultados");
  }, 1200);
  estadoAplicacion.simulacionActiva = { intervalo, tipo };
}

export function configurarProgreso() {
  const panel = document.querySelector("#panel-confirmar-envio");
  let preparacion = null;
  let campanaPreparada = null;
  let focoAnterior = null;
  const mostrarErrorEnvio = (error) => {
    panel.hidden = true;
    preparacion = null;
    campanaPreparada = null;
    for (const id of ["#aviso-envio-pendiente", "#aviso-envio-movil"]) {
      const aviso = document.querySelector(id);
      aviso.textContent = error.message;
      aviso.hidden = false;
    }
  };
  const cerrar = (restaurarFoco = true) => {
    panel.hidden = true;
    preparacion = null;
    campanaPreparada = null;
    void turno.liberar();
    if (restaurarFoco) focoAnterior?.focus();
  };
  panel.querySelectorAll("[data-cerrar-confirmacion]").forEach((boton) => boton.addEventListener("click", () => cerrar()));
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
  const turno = crearTurnoEnvio(
    asegurarSeleccionGuardada,
    async (campanaId, sigueVigente, botonOrigen) => {
      campanaPreparada = campanaId;
      preparacion = await prepararEnvio(campanaId);
      if (!sigueVigente()) return;
      const fila = (empresa, omitida = false) => {
        const item = document.createElement("li");
        const nombre = document.createElement("strong");
        const datos = document.createElement("span");
        nombre.textContent = empresa.nombre_empresa;
        datos.textContent = `${empresa.ubicacion} · ${empresa.correo}`;
        item.append(nombre, datos);
        if (omitida) {
          const motivo = document.createElement("small");
          motivo.textContent = empresa.motivo;
          item.append(motivo);
        }
        return item;
      };
      document.querySelector("#remitente-confirmacion").textContent = preparacion.remitente;
      document.querySelector("#destinatarios-confirmacion").replaceChildren(...preparacion.aptos.map((empresa) => fila(empresa)));
      document.querySelector("#lista-omitidos-confirmacion").replaceChildren(...preparacion.omitidos.map((empresa) => fila(empresa, true)));
      document.querySelector("#omitidos-confirmacion").hidden = preparacion.omitidos.length === 0;
      document.querySelector("#asunto-confirmacion").textContent = preparacion.asunto;
      document.querySelector("#cuerpo-confirmacion").textContent = preparacion.cuerpo;
      document.querySelector("#archivos-confirmacion").textContent = preparacion.archivos.join(", ") || "Ninguno";
      document.querySelector("#error-confirmacion").hidden = true;
      const confirmar = document.querySelector("#confirmar-envio-real");
      confirmar.disabled = preparacion.aptos.length === 0;
      confirmar.textContent = preparacion.aptos.length
        ? `Confirmar y enviar a ${preparacion.aptos.length} ${preparacion.aptos.length === 1 ? "empresa" : "empresas"}`
        : "Sin destinatarios aptos";
      focoAnterior = botonOrigen;
      panel.hidden = false;
      panel.querySelector(".boton_icono").focus();
    },
    mostrarErrorEnvio,
  );
  const iniciarEnvio = () => {
    if (document.querySelector("#iniciar-simulacion").dataset.modoConsulta === "sgva") {
      void turno.iniciar();
      return;
    }
    iniciarSimulacion("envio");
  };
  document.querySelector("#confirmar-envio-real").addEventListener("click", async () => {
    if (!preparacion || !campanaPreparada) return;
    const boton = document.querySelector("#confirmar-envio-real");
    boton.disabled = true;
    boton.textContent = "Autorizando envío…";
    try {
      await confirmarEnvio(campanaPreparada, preparacion.aptos.map(({ id }) => id), preparacion.confirmacion);
      const campanaId = campanaPreparada;
      turno.completado();
      cerrar(false);
      iniciarSeguimiento(campanaId, "envio");
    } catch (error) {
      cerrar(false);
      mostrarErrorEnvio(error);
    }
  });
  document.querySelector("#iniciar-simulacion").addEventListener("click", iniciarEnvio);
  document.querySelector("#iniciar-envio-movil").addEventListener("click", iniciarEnvio);
  const cancelarProceso = async (evento) => {
    const activa = campanaEnSeguimiento();
    if (activa) {
      const boton = evento.currentTarget;
      boton.disabled = true;
      try {
        const estado = await cancelarCampana(activa.id);
        detenerSeguimiento();
        document.querySelector("#reanudar-campana").hidden = true;
        document.querySelector("#formulario-campana").dataset.campanaId = "";
        const aviso = document.querySelector("#aviso-cancelacion");
        aviso.textContent = estado.estado !== "cancelada"
          ? `El proceso ya terminó: ${estado.etapa}. Puedes corregir los datos y crear otra búsqueda.`
          : activa.tipo === "envio"
          ? "Se detuvieron los mensajes pendientes. Los ya confirmados permanecen en Gmail."
          : "La consulta se canceló. Puedes corregir tus datos y volver a buscar.";
        aviso.hidden = false;
        irA("campana");
      } catch (error) {
        mostrarErrorProceso("servicio", error.message);
      } finally {
        boton.disabled = false;
      }
      return;
    }
    if (!estadoAplicacion.simulacionActiva) {
      irA("campana");
      return;
    }
    clearInterval(estadoAplicacion.simulacionActiva.intervalo);
    detenerDatosDuranteEspera();
    estadoAplicacion.simulacionActiva = null;
    irA("confirmacion");
  };
  document.querySelector("#cancelar-simulacion").addEventListener("click", cancelarProceso);
  document.querySelector("#cancelar-espera").addEventListener("click", cancelarProceso);
  window.addEventListener("hashchange", () => {
    if (estadoAplicacion.simulacionActiva && window.location.hash !== "#progreso") {
      clearInterval(estadoAplicacion.simulacionActiva.intervalo);
      detenerDatosDuranteEspera();
      estadoAplicacion.simulacionActiva = null;
    }
  });
  document.querySelector("#crear-otra-busqueda").addEventListener("click", async () => {
    const aviso = document.querySelector("#aviso-espera-gratis");
    if (document.querySelector("#resultados").dataset.modoConsulta === "sgva") {
      try {
        const respuesta = await fetch("/api/v1/disponibilidad", { credentials: "same-origin", cache: "no-store" });
        if (!respuesta.ok) throw new Error("No pudimos verificar cuándo puedes crear otra búsqueda.");
        const disponibilidad = await respuesta.json();
        if (!disponibilidad.puede_buscar) {
          const fecha = new Intl.DateTimeFormat("es-CO", { dateStyle: "long" }).format(new Date(disponibilidad.proxima_fecha));
          aviso.textContent = `Tu plan gratis permite otra campaña con envíos desde el ${fecha}.`;
          aviso.hidden = false;
          aviso.scrollIntoView({ block: "center", behavior: "smooth" });
          return;
        }
      } catch (error) {
        aviso.textContent = error.message;
        aviso.hidden = false;
        return;
      }
      aviso.hidden = true;
      irA("campana");
      return;
    }
    if (document.querySelector("#plan-campana").value === "gratis" && estadoAplicacion.proximaBusquedaGratis > new Date()) {
      aviso.textContent = textoEspera();
      aviso.hidden = false;
      aviso.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    aviso.hidden = true;
    irA("campana");
  });
}

