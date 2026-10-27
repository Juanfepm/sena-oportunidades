import { asegurarSeleccionGuardada, configurarCoincidencias, pintarResumen } from "./coincidencias.js";
import { configurarAutenticacion } from "./autenticacion.js";
import { cancelarCampana, confirmarEnvio, consultarCampana, guardarContenidoTemporal, guardarPreferencias, iniciarCampana, prepararEnvio } from "./campanas.js";
import { configurarErrores, mostrarErrorProceso } from "./errores.js";
import { configurarPruebaGmail } from "./prueba-gmail.js";
import { configurarPremium } from "./premium.js";
import { configurarRutas, irA } from "./rutas.js";
import { campanaEnSeguimiento, configurarSeguimiento, detenerDatosDuranteEspera, detenerSeguimiento, iniciarDatosDuranteEspera, iniciarSeguimiento } from "./seguimiento.js";
import { configurarUbicaciones } from "./ubicaciones.js";
import { crearTurnoEnvio } from "./turno-envio.js";
import { activarCorreccion, validarAdjuntos, validarFormulario } from "./validacion.js";

const etapas = {
  envio: [
    "Selección aprobada en esta demostración",
    "Comprobación ilustrativa de destinatarios",
    "Preparación simulada de mensajes",
    "Resumen de ejemplo listo",
  ],
};

let simulacionActiva = null;
let proximaBusquedaGratis = null;
let consultaSgvaActiva = false;

async function configurarConsultaSgva() {
  try {
    const respuesta = await fetch("/api/v1/capacidades", { cache: "no-store" });
    if (!respuesta.ok) return;
    const capacidades = await respuesta.json();
    consultaSgvaActiva = capacidades.sgva === true;
    if (!consultaSgvaActiva) return;
    document.querySelector(".aviso_prototipo").textContent = "Los mensajes a empresas salen de tu Gmail tras tu confirmación. El resumen llega desde debupawebapp@gmail.com.";
    document.querySelector("#como-funciona .paso_tarjeta:last-child p").textContent = "Los mensajes autorizados saldrán desde tu Gmail. DEBUPA enviará el resumen de contactos desde su correo; el historial evita recontactos durante seis meses.";
    const opcionIa = document.querySelector("#opcion-ia");
    const aceptarIa = document.querySelector("#aceptar-ia");
    // Cuando Gemini está habilitado, la autorización es obligatoria tanto en la vista como en la API.
    opcionIa.hidden = capacidades.clasificacion_ia !== true;
    aceptarIa.required = capacidades.clasificacion_ia === true;
    const documento = document.querySelector("#numero-documento");
    const clave = document.querySelector("#clave-sgva");
    for (const campo of [documento, clave]) { campo.disabled = false; campo.required = true; }
    documento.pattern = "[0-9]{5,15}";
    documento.maxLength = 15;
    documento.placeholder = "Tu número de documento";
    clave.placeholder = "Tu contraseña de SGVA";
    documento.nextElementSibling.textContent = "Se usa solo durante la consulta.";
    clave.nextElementSibling.textContent = "Se borra del formulario al iniciar y no se guarda en la base de datos.";
    documento.addEventListener("input", () => {
      const posicion = documento.selectionStart;
      const valorAnterior = documento.value;
      documento.value = valorAnterior.replace(/[^0-9]/g, "").slice(0, 15);
      if (posicion !== null) documento.setSelectionRange(Math.min(posicion, documento.value.length), Math.min(posicion, documento.value.length));
    });
    documento.addEventListener("keydown", (evento) => {
      if (evento.ctrlKey || evento.metaKey || evento.altKey) return;
      const teclasEdicion = new Set(["Backspace", "Delete", "ArrowLeft", "ArrowRight", "Home", "End", "Tab"]);
      if (!/^\d$/.test(evento.key) && !teclasEdicion.has(evento.key)) evento.preventDefault();
    });
    documento.addEventListener("paste", (evento) => {
      const texto = evento.clipboardData?.getData("text") ?? "";
      if (/[^0-9]/.test(texto)) evento.preventDefault();
    });
    document.querySelector("#formulario-correo button[type='submit']").textContent = "Consultar ofertas en SGVA";
    document.querySelector(".correo_borrador").textContent = "Se enviará solo tras tu confirmación";
    document.querySelector("#progreso .progreso_principal .ceja").textContent = "Consulta de SGVA";
    document.querySelector("#progreso h1").textContent = "Buscando ofertas visibles para ti.";
    document.querySelector("#progreso .panel_ayuda_progreso p").textContent = "Las consultas esperan su turno y su estado permanece disponible en tu cuenta mientras el servidor siga activo.";
    document.querySelector("#progreso .nota_fina").textContent = "Se lee SGVA sin postularte y sin enviar correos.";
    document.querySelector("#campana .aviso_requisitos small").textContent = "DEBUPA todavía no puede comprobar por sí solo si tienes patrocinio o una postulación activa.";
    document.querySelector("#campana .grupo_campo .ayuda_grupo").textContent = "Introduce tus credenciales una vez por consulta; se descartan al terminar y no se guardan en la base de datos.";
  } catch { /* La vista de demostración permanece disponible. */ }
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
    document.querySelector("#aviso-cancelacion").hidden = true;
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
    formularioCorreo.querySelector("button[type='submit']").firstChild.textContent = consultaSgvaActiva
      ? "Consultar ofertas en SGVA "
      : "Iniciar búsqueda de ejemplo ";
    irA("correo");
  });

  const formularioCorreo = document.querySelector("#formulario-correo");
  const erroresCorreo = document.querySelector("#errores-correo");
  const entradaArchivos = document.querySelector("#archivos-correo");
  const listaArchivos = document.querySelector("#lista-archivos");
  const limpiarCorreo = () => {
    formularioCorreo.reset();
    listaArchivos.replaceChildren();
    erroresCorreo.textContent = "";
    erroresCorreo.hidden = true;
  };
  window.addEventListener("hashchange", () => {
    if (window.location.hash === "#correo") limpiarCorreo();
  });
  document.querySelector("#confirmacion .resumen_revision a[href='#correo']").addEventListener("click", (evento) => {
    evento.preventDefault();
    formularioCorreo.querySelector("button[type='submit']").firstChild.textContent = "Guardar cambios del mensaje ";
    irA("correo");
  });
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
  formularioCorreo.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const archivosValidos = validarAdjuntos(entradaArchivos, erroresCorreo, listaArchivos, limiteArchivos());
    if (!archivosValidos) return;
    if (!validarFormulario(formularioCorreo, erroresCorreo)) return;
    const campanaId = formularioCampana.dataset.campanaId;
    if (!campanaId) {
      mostrarErrorProceso("servicio", "Guarda primero las preferencias de esta campaña.");
      return;
    }
    const boton = formularioCorreo.querySelector("button[type='submit']");
    boton.disabled = true;
    try {
      if (consultaSgvaActiva) {
        const estadoActual = await consultarCampana(campanaId);
        if (estadoActual.estado === "esperando_confirmacion") {
          await guardarContenidoTemporal(campanaId, formularioCampana, formularioCorreo);
          irA("confirmacion");
          return;
        }
      }
      const aceptaIa = document.querySelector("#aceptar-ia").checked;
      const acceso = consultaSgvaActiva ? {
        numero_documento: formularioCampana.elements.numero_documento.value.trim(),
        clave_sgva: formularioCampana.elements.clave_sgva.value,
        acepta_ia: aceptaIa,
        ...(aceptaIa ? { perfil_ia: {
          habilidades: formularioCampana.elements.habilidades.value.trim(),
          actividades_deseadas: formularioCampana.elements.actividades_deseadas.value.trim(),
          actividades_no_deseadas: formularioCampana.elements.actividades_no_deseadas.value.trim(),
        } } : {}),
      } : null;
      if (consultaSgvaActiva) await guardarContenidoTemporal(campanaId, formularioCampana, formularioCorreo);
      await iniciarCampana(campanaId, acceso);
      if (acceso) {
        formularioCampana.elements.numero_documento.value = "";
        formularioCampana.elements.clave_sgva.value = "";
      }
      iniciarSeguimiento(campanaId);
    } catch (error) {
      mostrarErrorProceso("servicio", error.message);
    } finally {
      boton.disabled = false;
    }
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
    simulacionActiva = null;
    pintarResumen(document.querySelector("#plan-campana").value);
    if (document.querySelector("#plan-campana").value === "gratis") {
      proximaBusquedaGratis = fechaUnMesDespues(new Date());
    }
    irA("resultados");
  }, 1200);
  simulacionActiva = { intervalo, tipo };
}

function configurarSimulacion() {
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
    if (!simulacionActiva) {
      irA("campana");
      return;
    }
    clearInterval(simulacionActiva.intervalo);
    detenerDatosDuranteEspera();
    simulacionActiva = null;
    irA("confirmacion");
  };
  document.querySelector("#cancelar-simulacion").addEventListener("click", cancelarProceso);
  document.querySelector("#cancelar-espera").addEventListener("click", cancelarProceso);
  window.addEventListener("hashchange", () => {
    if (simulacionActiva && window.location.hash !== "#progreso") {
      clearInterval(simulacionActiva.intervalo);
      detenerDatosDuranteEspera();
      simulacionActiva = null;
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

if (["correo", "confirmacion", "espera", "progreso", "resultados"].includes(window.location.hash.slice(1))) {
  window.history.replaceState(null, "", "#inicio");
}

document.querySelector("#anio-actual").textContent = String(new Date().getFullYear());
configurarRutas();
configurarPruebaGmail();
configurarAutenticacion();
configurarPremium();
configurarConsultaSgva();
configurarUbicaciones();
configurarCookies();
configurarCoincidencias();
configurarErrores();
configurarFormularios();
configurarSimulacion();
configurarSeguimiento();
