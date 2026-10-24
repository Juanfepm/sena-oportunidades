# Criterios de experiencia para Rumbo

## Fuentes estudiadas

- [Instructivo SGVA para aprendices, SENA (2022)](https://caprendizaje.sena.edu.co/sgva/APRENDICES/pag/ManualSGVAAprendices.pdf).
- [Diez heurísticas de usabilidad, Jakob Nielsen / Nielsen Norman Group](https://www.nngroup.com/articles/ten-usability-heuristics/).
- [Recomendaciones para interfaces con resultados de aprendizaje automático, Nielsen Norman Group](https://www.nngroup.com/articles/machine-learning-ux/).
- [Guía de alertas accesibles, W3C WAI](https://www.w3.org/WAI/ARIA/apg/patterns/alert/).
- [Infografía de 50 sesgos cognitivos, recopilación difundida por Visual Capitalist](https://www.visualcapitalist.com/50-cognitive-biases-in-the-modern-world/).

La cifra de 50 corresponde a esa recopilación divulgativa, no a una lista científica única u oficial. Los sesgos son una herramienta para detectar decisiones de diseño problemáticas, no para manipular al aprendiz.

## Lo que confirma el manual del SGVA

- El aprendiz entra en la opción «Aprendiz» y busca ofertas visibles para su perfil.
- «Buscar empresas» permite filtrar por nombre y ubicación; se debe pulsar «Buscar» para aplicar el filtro.
- Los detalles aparecen antes de la acción «Aplicar».
- Una aplicación activa limita nuevas postulaciones hasta que termine el proceso o se cumplan las condiciones descritas en el manual.
- El SGVA permite actualizar el perfil profesional y ver mensajes de empresas.

Rumbo toma únicamente el flujo de consulta y lectura como referencia. Contactar externamente por correo y postularse dentro del SGVA se explican como acciones diferentes. El prototipo no implementa ninguna de las dos.

## Decisiones observables en la interfaz

| Principio o riesgo | Aplicación |
| --- | --- |
| Estado visible | La cola, la búsqueda, la revisión y el envío tienen estados separados. En la vista previa se rotulan como simulados. |
| Lenguaje cercano | «Empresas sugeridas», «Revisar» y «Quitar» reemplazan términos técnicos internos. |
| Control y libertad | El aprendiz puede volver, editar el correo, retirar destinatarios y detener la demostración. |
| Consistencia | Botones primarios verdes, secundarios claros y una misma estructura de formularios. |
| Prevención de errores | Selectores para modalidad y tiempo, dependencias departamento/ciudad, límites de archivos y confirmación previa. |
| Reconocimiento | Etiquetas visibles, ayudas junto al campo y un resumen del motivo de coincidencia. |
| Diseño mínimo | La pantalla principal se centra en la búsqueda; los detalles quedan en pasos posteriores. |
| Recuperación | Alertas persistentes explican qué corregir, sin desaparecer automáticamente. |
| Ayuda contextual | Se aclara qué significa «remoto por confirmar» y que contactar no equivale a «Aplicar». |
| Sesgo de automatización | La puntuación se acompaña de motivo, límite e intervención humana antes del envío. |
| Anclaje en porcentajes | El porcentaje del ejemplo se rotula como estimado; el producto real deberá calibrarlo con datos antes de presentarlo. |
| Sesgo de confirmación | La revisión muestra información insuficiente y dudas, no solo razones favorables. |
| Efecto de posición y disponibilidad | El orden de resultados deberá explicarse y la lista no debe ocultar opciones relevantes por una cuota comercial. |
| Efecto de encuadre | Gratis y premium indican límites reales, sin prometer una cantidad mínima si no existen ofertas afines. |

## Reglas de contenido y seguridad

- No presentar modalidad remota como confirmada si la empresa no lo ha escrito expresamente.
- No usar urgencia artificial, temporizadores de presión o selección oculta de destinatarios.
- No guardar contraseñas ni adjuntos en el navegador. Los campos SGVA están desactivados en la vista previa.
- Renderizar texto variable con `textContent`; no insertar contenido del usuario con `innerHTML`.
- Validar tipo, cantidad y tamaño de archivos también en el servidor cuando exista.
- Mantener las páginas de privacidad, cookies y condiciones como borradores señalados hasta su revisión para el piloto.
- El panel de administración necesitará control de acceso en el backend antes de manejar datos.
