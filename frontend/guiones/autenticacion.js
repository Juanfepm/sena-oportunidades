const estadoCuenta = document.querySelector("#estado-cuenta");
const enlaceGoogle = document.querySelector("#iniciar-google");
const botonCerrar = document.querySelector("#cerrar-sesion");

async function obtenerJson(ruta) {
  const respuesta = await fetch(ruta, { cache: "no-store", credentials: "same-origin" });
  if (!respuesta.ok) return { codigo: respuesta.status, datos: null };
  return { codigo: respuesta.status, datos: await respuesta.json() };
}

async function actualizarCuenta() {
  try {
    const cuenta = await obtenerJson("/api/v1/autenticacion/yo");
    if (cuenta.datos) {
      const nombre = cuenta.datos.nombre || cuenta.datos.correo;
      estadoCuenta.textContent = `${nombre} · ${cuenta.datos.plan}`;
      estadoCuenta.title = cuenta.datos.correo;
      enlaceGoogle.hidden = true;
      botonCerrar.hidden = false;
      return;
    }

    const capacidades = await obtenerJson("/api/v1/capacidades");
    const disponible = capacidades.datos?.google_oauth === true;
    estadoCuenta.textContent = disponible ? "Sin sesión" : "Google aún no está configurado";
    estadoCuenta.removeAttribute("title");
    enlaceGoogle.hidden = !disponible;
    botonCerrar.hidden = true;
  } catch {
    estadoCuenta.textContent = "Abre DEBUPA desde la API para iniciar sesión";
    enlaceGoogle.hidden = true;
    botonCerrar.hidden = true;
  }
}

export function configurarAutenticacion() {
  botonCerrar.addEventListener("click", async () => {
    botonCerrar.disabled = true;
    estadoCuenta.textContent = "Cerrando sesión…";
    try {
      const respuesta = await fetch("/api/v1/autenticacion/cerrar-sesion", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!respuesta.ok) throw new Error("No se pudo cerrar la sesión.");
      await actualizarCuenta();
    } catch {
      estadoCuenta.textContent = "No se pudo cerrar la sesión. Intenta de nuevo.";
    } finally {
      botonCerrar.disabled = false;
    }
  });
  actualizarCuenta();
}
