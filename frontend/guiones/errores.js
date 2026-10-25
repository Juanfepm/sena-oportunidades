const dialogo = document.querySelector("#alerta-proceso");
const texto = document.querySelector("#texto-alerta-proceso");
const ayudaSgva = document.querySelector("#ayuda-alerta-sgva");

export function mostrarErrorProceso(codigo, detalle) {
  texto.textContent = detalle || "Inténtalo nuevamente dentro de unos minutos.";
  ayudaSgva.hidden = codigo !== "sgva_restringido";
  if (!dialogo.open) dialogo.showModal();
  document.querySelector("#cerrar-alerta-proceso").focus();
}

export function configurarErrores() {
  document.querySelector("#cerrar-alerta-proceso").addEventListener("click", () => dialogo.close());
  dialogo.addEventListener("click", (evento) => {
    if (evento.target === dialogo) dialogo.close();
  });
}
