import { guardarContenidoTemporal, guardarPreferencias, iniciarCampana, consultarCampana } from "./campanas.js";
import { mostrarErrorProceso } from "./errores.js";
import { irA } from "./rutas.js";
import { iniciarSeguimiento } from "./seguimiento.js";
import { estadoAplicacion } from "./estado-aplicacion.js";
import { textoEspera } from "./progreso.js";
import { activarCorreccion, validarAdjuntos, validarFormulario } from "./validacion.js";

export function configurarFormularios() {
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
    if (formularioCampana.elements.plan.value === "gratis" && estadoAplicacion.proximaBusquedaGratis > new Date()) {
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
    formularioCorreo.querySelector("button[type='submit']").firstChild.textContent = estadoAplicacion.consultaSgvaActiva
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
      if (estadoAplicacion.consultaSgvaActiva) {
        const estadoActual = await consultarCampana(campanaId);
        if (estadoActual.estado === "esperando_confirmacion") {
          await guardarContenidoTemporal(campanaId, formularioCampana, formularioCorreo);
          irA("confirmacion");
          return;
        }
      }
      const aceptaIa = document.querySelector("#aceptar-ia").checked;
      const acceso = estadoAplicacion.consultaSgvaActiva ? {
        numero_documento: formularioCampana.elements.numero_documento.value.trim(),
        clave_sgva: formularioCampana.elements.clave_sgva.value,
        acepta_ia: aceptaIa,
        ...(aceptaIa ? { perfil_ia: {
          habilidades: formularioCampana.elements.habilidades.value.trim(),
          actividades_deseadas: formularioCampana.elements.actividades_deseadas.value.trim(),
          actividades_no_deseadas: formularioCampana.elements.actividades_no_deseadas.value.trim(),
        } } : {}),
      } : null;
      if (estadoAplicacion.consultaSgvaActiva) await guardarContenidoTemporal(campanaId, formularioCampana, formularioCorreo);
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

