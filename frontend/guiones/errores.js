const dialogo = document.querySelector("#alerta-proceso");
const texto = document.querySelector("#texto-alerta-proceso");
const titulo = document.querySelector("#titulo-alerta-proceso");
const ayudaSgva = document.querySelector("#ayuda-alerta-sgva");
let destinoAlCerrar = null;

export function mostrarErrorProceso(codigo, detalle, destino = null) {
  const titulos = {
    sgva_sin_conexion: "No pudimos conectar con SGVA",
    sgva_caido: "SGVA está fuera de servicio",
  };
  titulo.textContent = titulos[codigo] || "No pudimos completar el proceso";
  texto.textContent = detalle || "Inténtalo nuevamente dentro de unos minutos.";
  ayudaSgva.hidden = codigo !== "sgva_restringido";
  destinoAlCerrar = destino;
  if (!dialogo.open) dialogo.showModal();
  document.querySelector("#cerrar-alerta-proceso").focus();
}

export function configurarErrores() {
  document.querySelector("#cerrar-alerta-proceso").addEventListener("click", () => dialogo.close());
  dialogo.addEventListener("close", () => {
    if (destinoAlCerrar) window.location.hash = destinoAlCerrar;
    destinoAlCerrar = null;
  });
  dialogo.addEventListener("click", (evento) => {
    if (evento.target === dialogo) dialogo.close();
  });
}
