import { configurarCoincidencias, pintarResumen } from "./coincidencias.js";
import { configurarAutenticacion } from "./autenticacion.js";
import { configurarBorradoresTemporales } from "./borradores-temporales.js";
import { borrarContenidoTemporal, guardarContenidoTemporal, guardarPreferencias, iniciarCampana } from "./campanas.js";
import { configurarErrores, mostrarErrorProceso } from "./errores.js";
import { configurarPruebaGmail } from "./prueba-gmail.js";
import { configurarRutas, irA } from "./rutas.js";
import { configurarSeguimiento, detenerDatosDuranteEspera, detenerSeguimiento, haySeguimiento, iniciarDatosDuranteEspera, iniciarSeguimiento } from "./seguimiento.js";
import { configurarUbicaciones } from "./ubicaciones.js";
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
    document.querySelector("#opcion-ia").hidden = capacidades.clasificacion_ia !== true;
    const documento = document.querySelector("#numero-documento");
    const clave = document.querySelector("#clave-sgva");
    for (const campo of [documento, clave]) { campo.disabled = false; campo.required = true; }
    documento.pattern = "[0-9]{5,15}";
    documento.maxLength = 15;
    documento.placeholder = "Tu número de documento";
    clave.placeholder = "Tu contraseña de SGVA";
    documento.nextElementSibling.textContent = "Se usa solo durante la consulta.";
    clave.nextElementSibling.textContent = "Se borra del formulario al iniciar y no se guarda en la base de datos.";
    document.querySelector("#formulario-correo button[type='submit']").textContent = "Consultar ofertas en SGVA";
    document.querySelector(".correo_borrador").textContent = "Borrador sin envío";
    document.querySelector(".correo_temporal > p").textContent = "Puedes guardar este borrador cifrado durante 24 horas y eliminarlo cuando quieras. La consulta de SGVA no enviará mensajes a empresas.";
    document.querySelector("#progreso .progreso_principal .ceja").textContent = "Consulta de SGVA";
    document.querySelector("#progreso h1").textContent = "Buscando ofertas visibles para ti.";
    document.querySelector("#progreso .panel_ayuda_progreso p").textContent = "Las consultas esperan su turno y su estado permanece disponible en tu cuenta mientras el servidor siga activo.";
    document.querySelector("#progreso .nota_fina").textContent = "Se lee SGVA sin postularte y sin enviar correos.";
    document.querySelector("#campana .aviso_requisitos small").textContent = "DEBUPA todavía no puede comprobar por sí solo si tienes patrocinio o una postulación activa.";
    document.querySelector("#campana .grupo_campo .ayuda_grupo").textContent = "Introduce tus credenciales una vez por consulta; se descartan al terminar y no se guardan en la base de datos.";
    document.querySelector("#privacidad .texto_legal h2:last-of-type + p").textContent = "El inicio de sesión guarda tu identificador, nombre y correo verificado; también vincula el permiso de Gmail. Documento, contraseña SGVA y perfil usado para IA permanecen solo en memoria durante la consulta. Si autorizas IA, se envían a Gemini únicamente tus intereses y el texto de funciones de las ofertas, sin credenciales, correos ni teléfonos. En el nivel gratuito Google puede usar estos textos para mejorar sus productos. Se guardan las ofertas y puntuaciones para que las revises. No se postula al aprendiz ni se contacta a empresas en esta etapa.";
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
      botonBorrarTemporal.hidden = true;
      estadoTemporal.textContent = "";
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
    irA("correo");
  });

  const formularioCorreo = document.querySelector("#formulario-correo");
  const erroresCorreo = document.querySelector("#errores-correo");
  const entradaArchivos = document.querySelector("#archivos-correo");
  const listaArchivos = document.querySelector("#lista-archivos");
  const botonGuardarTemporal = document.querySelector("#guardar-contenido-temporal");
  const botonBorrarTemporal = document.querySelector("#borrar-contenido-temporal");
  const estadoTemporal = document.querySelector("#estado-contenido-temporal");
  const guardarTemporal = async () => {
    const campanaId = formularioCampana.dataset.campanaId;
    if (!campanaId) {
      estadoTemporal.textContent = "Primero completa y guarda tus preferencias.";
      return;
    }
    if (!validarAdjuntos(entradaArchivos, erroresCorreo, listaArchivos, limiteArchivos())) return;
    if (!validarFormulario(formularioCorreo, erroresCorreo)) return;
    botonGuardarTemporal.disabled = true;
    estadoTemporal.textContent = "Guardando contenido cifrado…";
    try {
      const resumen = await guardarContenidoTemporal(campanaId, formularioCampana, formularioCorreo);
      const fecha = new Date(resumen.vence_en).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
      estadoTemporal.textContent = `Borrador cifrado guardado hasta el ${fecha}. No se ha enviado a empresas.`;
      botonBorrarTemporal.hidden = false;
      window.dispatchEvent(new CustomEvent("debupa:contenidos-actualizados", { detail: { campanaId, accion: "guardado" } }));
    } catch (error) {
      estadoTemporal.textContent = error instanceof Error ? error.message : "No se pudo guardar el borrador.";
    } finally {
      botonGuardarTemporal.disabled = false;
    }
  };
  botonGuardarTemporal.addEventListener("click", guardarTemporal);
  botonBorrarTemporal.addEventListener("click", async () => {
    botonBorrarTemporal.disabled = true;
    estadoTemporal.textContent = "Eliminando contenido guardado…";
    try {
      await borrarContenidoTemporal(formularioCampana.dataset.campanaId);
      botonBorrarTemporal.hidden = true;
      estadoTemporal.textContent = "Borrador temporal eliminado.";
      window.dispatchEvent(new CustomEvent("debupa:contenidos-actualizados", {
        detail: { campanaId: formularioCampana.dataset.campanaId, accion: "borrado" },
      }));
    } catch (error) {
      estadoTemporal.textContent = error instanceof Error ? error.message : "No se pudo eliminar el borrador.";
    } finally {
      botonBorrarTemporal.disabled = false;
    }
  });
  window.addEventListener("debupa:contenidos-actualizados", (evento) => {
    if (evento.detail?.accion === "borrado" && evento.detail.campanaId === formularioCampana.dataset.campanaId) {
      botonBorrarTemporal.hidden = true;
      estadoTemporal.textContent = "Borrador temporal eliminado.";
    }
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
  document.querySelector("#iniciar-simulacion").addEventListener("click", () => iniciarSimulacion("envio"));
  document.querySelector("#cancelar-simulacion").addEventListener("click", () => {
    if (haySeguimiento()) {
      detenerSeguimiento();
      irA("inicio");
      return;
    }
    if (!simulacionActiva) return;
    clearInterval(simulacionActiva.intervalo);
    detenerDatosDuranteEspera();
    simulacionActiva = null;
    irA("confirmacion");
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
configurarBorradoresTemporales();
configurarPruebaGmail();
configurarAutenticacion();
configurarConsultaSgva();
configurarUbicaciones();
configurarCookies();
configurarCoincidencias();
configurarErrores();
configurarFormularios();
configurarSimulacion();
configurarSeguimiento();
