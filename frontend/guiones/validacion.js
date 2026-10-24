const tiposPermitidos = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "image/jpeg",
  "image/png",
  "image/webp",
]);

const extensionesPermitidas = new Set(["pdf", "doc", "docx", "txt", "jpg", "jpeg", "png", "webp"]);

function mensajeCampo(campo) {
  const nodoEtiqueta = document.querySelector(`label[for="${campo.id}"]`) ?? campo.closest("label");
  const textoEtiqueta = nodoEtiqueta?.querySelector(".campo_opcional") ? nodoEtiqueta.firstChild.textContent : nodoEtiqueta?.textContent;
  const etiqueta = (textoEtiqueta?.trim() ?? "Este campo").replace(/[.:]+$/, "");
  if (campo.validity.customError) return `${etiqueta}: ${campo.validationMessage}`;
  if (campo.type === "checkbox" && campo.validity.valueMissing) return `${etiqueta}: marca esta casilla.`;
  if (campo.validity.valueMissing) return `${etiqueta}: completa este dato.`;
  if (campo.minLength > 0 && campo.value.length > 0 && campo.value.length < campo.minLength) {
    return `${etiqueta}: escribe al menos ${campo.minLength} caracteres.`;
  }
  if (campo.maxLength > 0 && campo.value.length > campo.maxLength) return `${etiqueta}: utiliza ${campo.maxLength} caracteres o menos.`;
  return `${etiqueta}: revisa el valor ingresado.`;
}

function mostrarErrores(contenedor, errores, origen) {
  contenedor.replaceChildren();
  contenedor.hidden = errores.length === 0;
  contenedor.dataset.origen = errores.length === 0 ? "" : origen;
  if (errores.length === 0) return;

  const titulo = document.createElement("strong");
  titulo.textContent = "Revisa estos datos para continuar:";
  const lista = document.createElement("ul");
  errores.forEach((mensaje) => {
    const elemento = document.createElement("li");
    elemento.textContent = mensaje;
    lista.append(elemento);
  });
  contenedor.append(titulo, lista);
}

export function validarFormulario(formulario, contenedorErrores) {
  const controles = [...formulario.querySelectorAll("input, select, textarea")].filter((campo) => !campo.disabled && campo.type !== "file");
  const errores = [];

  controles.forEach((campo) => {
    if (campo.type === "text" || campo.tagName === "TEXTAREA") {
      campo.value = campo.value.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "").trim();
    }
    const longitudInvalida = campo.minLength > 0 && campo.value.length > 0 && campo.value.length < campo.minLength;
    const esValido = campo.checkValidity() && !longitudInvalida;
    campo.setAttribute("aria-invalid", String(!esValido));
    if (!esValido) errores.push(mensajeCampo(campo));
  });

  mostrarErrores(contenedorErrores, errores, "formulario");
  if (errores.length > 0) {
    contenedorErrores.scrollIntoView({ block: "center", behavior: "smooth" });
    controles.find((campo) => !campo.checkValidity() || (campo.minLength > 0 && campo.value.length > 0 && campo.value.length < campo.minLength))?.focus({ preventScroll: true });
  }
  return errores.length === 0;
}

export function activarCorreccion(formulario, contenedorErrores) {
  const revisar = () => {
    if (contenedorErrores.hidden || contenedorErrores.dataset.origen !== "formulario") return;
    const camposInvalidos = [...formulario.querySelectorAll("input, select, textarea")]
      .filter((campo) => !campo.disabled && campo.type !== "file" && (!campo.checkValidity() || (campo.minLength > 0 && campo.value.length > 0 && campo.value.length < campo.minLength)));
    camposInvalidos.forEach((campo) => campo.setAttribute("aria-invalid", "true"));
    if (camposInvalidos.length === 0) mostrarErrores(contenedorErrores, [], "formulario");
  };
  formulario.addEventListener("input", revisar);
  formulario.addEventListener("change", revisar);
}

export function validarAdjuntos(entrada, contenedorErrores, listaArchivos, limiteArchivos) {
  const archivos = [...entrada.files];
  const errores = [];
  if (archivos.length > limiteArchivos) {
    errores.push(`Tu plan admite un máximo de ${limiteArchivos} ${limiteArchivos === 1 ? "archivo" : "archivos"}.`);
  }

  archivos.forEach((archivo) => {
    const extension = archivo.name.split(".").at(-1)?.toLowerCase();
    if (!extensionesPermitidas.has(extension) || (archivo.type && !tiposPermitidos.has(archivo.type))) {
      errores.push(`El archivo ${archivo.name} no tiene un formato permitido.`);
    }
    if (archivo.size > 5 * 1024 * 1024) errores.push(`El archivo ${archivo.name} supera los 5 MB.`);
  });

  if (errores.length > 0 || contenedorErrores.dataset.origen === "archivos") {
    mostrarErrores(contenedorErrores, errores, "archivos");
  }
  listaArchivos.replaceChildren();
  if (errores.length > 0) {
    entrada.value = "";
    return false;
  }

  archivos.forEach((archivo) => {
    const elemento = document.createElement("li");
    elemento.textContent = archivo.name;
    listaArchivos.append(elemento);
  });
  return true;
}
