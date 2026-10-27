const bytesPorMiB = 1024 * 1024;

async function optimizarImagen(archivo) {
  if (!archivo || !["image/png", "image/jpeg"].includes(archivo.type) || archivo.size > 8 * bytesPorMiB) {
    throw new Error("Elige una captura PNG o JPG de máximo 8 MB.");
  }

  const original = await createImageBitmap(archivo);
  const escala = Math.min(1, 1800 / Math.max(original.width, original.height));
  const lienzo = document.createElement("canvas");
  lienzo.width = Math.round(original.width * escala);
  lienzo.height = Math.round(original.height * escala);
  const contexto = lienzo.getContext("2d");
  contexto.fillStyle = "#ffffff";
  contexto.fillRect(0, 0, lienzo.width, lienzo.height);
  contexto.drawImage(original, 0, 0, lienzo.width, lienzo.height);
  original.close();

  const convertir = (calidad) => new Promise((resolver) => lienzo.toBlob(resolver, "image/jpeg", calidad));
  let resultado = await convertir(0.88);
  if (resultado?.size > 2 * bytesPorMiB) resultado = await convertir(0.72);
  if (!resultado || resultado.size > 2 * bytesPorMiB) {
    throw new Error("La imagen sigue pesando más de 2 MB. Prueba otra captura.");
  }
  return new File([resultado], "comprobante-optimizado.jpg", { type: "image/jpeg" });
}

export async function prepararComprobante(archivo) {
  if (archivo?.type !== "application/pdf") return optimizarImagen(archivo);
  if (!archivo.size || archivo.size > 2 * bytesPorMiB) {
    throw new Error("El PDF debe pesar como máximo 2 MB.");
  }
  return archivo;
}
