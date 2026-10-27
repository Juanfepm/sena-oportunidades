export function configurarCookies() {
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

