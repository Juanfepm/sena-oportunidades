"""Actualiza el catálogo local desde la DIVIPOLA oficial de datos.gov.co."""

import json
import unicodedata
from pathlib import Path
from urllib.request import urlopen


FUENTE = "https://www.datos.gov.co/resource/gdxc-w37w.json?$limit=2000"
RAIZ = Path(__file__).resolve().parents[1]
DESTINOS = (
    RAIZ / "frontend" / "datos" / "municipios.json",
    RAIZ / "backend" / "aplicacion" / "dominio" / "municipios.json",
)
DEPARTAMENTOS = {
    "05": "Antioquia", "08": "Atlántico", "11": "Bogotá D. C.", "13": "Bolívar",
    "15": "Boyacá", "17": "Caldas", "18": "Caquetá", "19": "Cauca",
    "20": "Cesar", "23": "Córdoba", "25": "Cundinamarca", "27": "Chocó",
    "41": "Huila", "44": "La Guajira", "47": "Magdalena", "50": "Meta",
    "52": "Nariño", "54": "Norte de Santander", "63": "Quindío", "66": "Risaralda",
    "68": "Santander", "70": "Sucre", "73": "Tolima", "76": "Valle del Cauca",
    "81": "Arauca", "85": "Casanare", "86": "Putumayo",
    "88": "San Andrés y Providencia", "91": "Amazonas", "94": "Guainía",
    "95": "Guaviare", "97": "Vaupés", "99": "Vichada",
}


def ordenar(texto: str) -> str:
    return "".join(caracter for caracter in unicodedata.normalize("NFD", texto.casefold())
                   if unicodedata.category(caracter) != "Mn")


def nombre_visible(nombre: str) -> str:
    if nombre == "BOGOTÁ, D.C.":
        return "Bogotá"
    palabras = nombre.strip().title().split()
    return " ".join(palabra.lower() if indice and palabra in {"De", "Del", "La", "Las", "Los", "Y"}
                    else palabra for indice, palabra in enumerate(palabras))


def actualizar() -> None:
    with urlopen(FUENTE, timeout=30) as respuesta:
        registros = json.load(respuesta)
    municipios = {nombre: set() for nombre in DEPARTAMENTOS.values()}
    for registro in registros:
        municipios[DEPARTAMENTOS[registro["cod_dpto"]]].add(nombre_visible(registro["nom_mpio"]))
    if len(registros) < 1100 or len(municipios) != 33 or any(not nombres for nombres in municipios.values()):
        raise ValueError("La respuesta DIVIPOLA está incompleta; se conserva el catálogo anterior.")
    contenido = {
        "fuente": FUENTE,
        "descripcion": "Municipios, isla y áreas no municipalizadas de DIVIPOLA; nombres adaptados para lectura.",
        "departamentos": {
            departamento: sorted(nombres, key=ordenar)
            for departamento, nombres in sorted(municipios.items(), key=lambda elemento: ordenar(elemento[0]))
        },
    }
    serializado = json.dumps(contenido, ensure_ascii=False, indent=2) + "\n"
    for destino in DESTINOS:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(serializado, encoding="utf-8")
    print(f"Catálogo guardado: {len(registros)} localidades en {len(municipios)} departamentos.")


if __name__ == "__main__":
    actualizar()
