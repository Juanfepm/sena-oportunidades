const mensajes = {
  "base-datos": ["No pudimos acceder a tus datos", "La base de datos no responde en este momento. Espera un momento y vuelve a intentarlo."],
  gmail: ["No pudimos vincular Gmail", "No recibimos el permiso de envío o no fue posible protegerlo. Vuelve a entrar con Google y acepta el permiso solicitado."],
  google: ["No pudimos iniciar sesión", "Google no completó la autorización. Comprueba tu conexión y vuelve a intentarlo."],
  servicio: ["Servicio temporalmente no disponible", "Uno de los servicios necesarios no respondió. Vuelve a intentarlo en unos minutos."],
  sgva: ["No pudimos consultar SGVA", "El SGVA no respondió. Inténtalo más tarde; si el acceso es rechazado, revisa tu situación directamente en SGVA."],
};

const tipo = new URLSearchParams(window.location.search).get("tipo");
const [titulo, detalle] = mensajes[tipo] ?? mensajes.servicio;
document.querySelector("#titulo-error").textContent = titulo;
document.querySelector("#detalle-error").textContent = detalle;
document.title = `${titulo} | DEBUPA`;
