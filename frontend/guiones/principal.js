import { configurarAutenticacion } from "./autenticacion.js";
import { configurarCoincidencias } from "./coincidencias.js";
import { configurarConsultaSgva } from "./consulta-sgva.js";
import { configurarCookies } from "./cookies.js";
import { configurarErrores } from "./errores.js";
import { configurarFormularios } from "./formularios.js";
import { configurarPremium } from "./premium.js";
import { configurarProgreso } from "./progreso.js";
import { configurarPruebaGmail } from "./prueba-gmail.js";
import { configurarRutas } from "./rutas.js";
import { configurarSeguimiento } from "./seguimiento.js";
import { configurarUbicaciones } from "./ubicaciones.js";

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
configurarProgreso();
configurarSeguimiento();
