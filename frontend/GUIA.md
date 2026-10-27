# Convenciones del frontend de DEBUPA

Los ejemplos `frentes.html`, `transporte.html` y sus hojas CSS inspiran la separación entre estructura, estilos y comportamiento. Aplicamos sus patrones útiles sin copiar sus colores, nombres ni reglas repetidas. Para JavaScript usamos [Clean Code JavaScript](https://github.com/ryanmcdermott/clean-code-javascript) como guía de legibilidad, no como norma rígida.

- HTML: un `main`, navegación y secciones con títulos claros; formularios etiquetados, estados accesibles y botones con `type`. Metadatos y estilos van en `head`; `principal.js` carga los demás módulos con `import`.
- Indentación HTML: usa dos espacios por nivel y coloca cada elemento hijo en una línea propia. Separa con una línea en blanco los bloques principales y no comprimas en una sola línea secciones, artículos, formularios, tarjetas ni diálogos con varios elementos.
- Nombres: identificadores `id-con-guiones`, clases `clase_con_guiones_bajos` y variables y funciones descriptivas en español. Los identificadores que utiliza el backend o la API mantienen su contrato.
- CSS: tokens compartidos en `variables.css`, reglas base en `base.css`, componentes reutilizables en `componentes.css`, páginas en `paginas.css` y pago/administración en `premium.css`. Dentro de cada hoja, mantener juntos los selectores de un componente y colocar las media queries al final. Evitar duplicados; respetar el orden de la cascada cuando una regla depende de otra.
- JavaScript: `principal.js` inicia la página; cada módulo concentra una responsabilidad. Mantener separados el acceso a API, la lógica de interfaz y la validación. Los datos externos se insertan como texto o nodos, nunca como HTML sin validar.
- Al refactorizar, conservar apariencia, rutas y respuestas de la API. Comprobar sintaxis, carga de módulos, navegación y ancho móvil y de escritorio. La validación del navegador complementa, pero no reemplaza, la del servidor.
