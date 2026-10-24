"""Actualiza una selección de municipios desde la DIVIPOLA oficial."""

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
MUNICIPIOS_PRINCIPALES = {
    "Amazonas": ("Leticia", "Puerto Nariño"),
    "Antioquia": ("Medellín", "Bello", "Envigado", "Itagüí", "Rionegro"),
    "Arauca": ("Arauca", "Saravena", "Tame"),
    "Atlántico": ("Barranquilla", "Soledad", "Malambo"),
    "Bogotá D. C.": ("Bogotá",),
    "Bolívar": ("Cartagena de Indias", "Magangué", "Turbaco"),
    "Boyacá": ("Tunja", "Duitama", "Sogamoso"),
    "Caldas": ("Manizales", "La Dorada", "Chinchiná"),
    "Caquetá": ("Florencia", "San Vicente del Caguán"),
    "Casanare": ("Yopal", "Aguazul", "Villanueva"),
    "Cauca": ("Popayán", "Santander de Quilichao"),
    "Cesar": ("Valledupar", "Aguachica"),
    "Chocó": ("Quibdó", "Istmina"),
    "Córdoba": ("Montería", "Cereté", "Lorica"),
    "Cundinamarca": ("Soacha", "Chía", "Facatativá", "Zipaquirá"),
    "Guainía": ("Inírida",),
    "Guaviare": ("San José del Guaviare",),
    "Huila": ("Neiva", "Pitalito", "Garzón"),
    "La Guajira": ("Riohacha", "Maicao", "Uribia"),
    "Magdalena": ("Santa Marta", "Ciénaga"),
    "Meta": ("Villavicencio", "Acacías", "Granada"),
    "Nariño": ("Pasto", "Ipiales", "San Andrés de Tumaco"),
    "Norte de Santander": ("San José de Cúcuta", "Ocaña", "Villa del Rosario"),
    "Putumayo": ("Mocoa", "Puerto Asís"),
    "Quindío": ("Armenia", "Calarcá", "Montenegro"),
    "Risaralda": ("Pereira", "Dosquebradas", "Santa Rosa de Cabal"),
    "San Andrés y Providencia": ("San Andrés", "Providencia"),
    "Santander": ("Bucaramanga", "Floridablanca", "Barrancabermeja"),
    "Sucre": ("Sincelejo", "Corozal"),
    "Tolima": ("Ibagué", "Espinal", "Melgar"),
    "Valle del Cauca": ("Santiago de Cali", "Palmira", "Buenaventura", "Tuluá"),
    "Vaupés": ("Mitú",),
    "Vichada": ("Puerto Carreño",),
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


def seleccionar_municipios(municipios: dict[str, set[str]]) -> dict[str, list[str]]:
    if set(municipios) != set(MUNICIPIOS_PRINCIPALES):
        raise ValueError("La selección no coincide con los departamentos de DIVIPOLA.")
    seleccion = {}
    for departamento, nombres in MUNICIPIOS_PRINCIPALES.items():
        no_encontrados = set(nombres) - municipios[departamento]
        if no_encontrados:
            raise ValueError(f"Municipios no encontrados en {departamento}: {sorted(no_encontrados)}")
        seleccion[departamento] = sorted(nombres, key=ordenar)
    return dict(sorted(seleccion.items(), key=lambda elemento: ordenar(elemento[0])))


def guardar_municipios(municipios: dict[str, list[str]]) -> None:
    contenido = {
        "fuente": FUENTE,
        "descripcion": "Selección práctica de ciudades y municipios principales verificados con DIVIPOLA; no es un ranking oficial.",
        "departamentos": municipios,
    }
    serializado = json.dumps(contenido, ensure_ascii=False, indent=2) + "\n"
    for destino in DESTINOS:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(serializado, encoding="utf-8")
    print(f"Catálogo guardado: {sum(map(len, municipios.values()))} municipios en {len(municipios)} departamentos.")


def actualizar() -> None:
    with urlopen(FUENTE, timeout=30) as respuesta:
        registros = json.load(respuesta)
    municipios = {nombre: set() for nombre in DEPARTAMENTOS.values()}
    for registro in registros:
        municipios[DEPARTAMENTOS[registro["cod_dpto"]]].add(nombre_visible(registro["nom_mpio"]))
    if len(registros) < 1100 or len(municipios) != 33 or any(not nombres for nombres in municipios.values()):
        raise ValueError("La respuesta DIVIPOLA está incompleta; se conserva el catálogo anterior.")
    guardar_municipios(seleccionar_municipios(municipios))


if __name__ == "__main__":
    actualizar()
