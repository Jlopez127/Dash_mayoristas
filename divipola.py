"""
divipola.py — DIVIPOLA (DANE): departamentos y municipios de Colombia, VENDORIZADO.

Fuente vendorizada en divipola_colombia.json (mismo directorio). La app NO consulta
internet en runtime para esto. El JSON tiene, por municipio:
    {"departamento", "codigo_dpto" (2 díg), "municipio", "codigo_mpio" (5 díg DIVIPOLA)}

Uso típico (selector que muestra NOMBRES y resuelve CÓDIGOS por detrás):
    from divipola import selector_divipola
    state_code, city_code = selector_divipola("cli_new")   # (None, None) si falta selección
"""
import json
import os
from functools import lru_cache

try:
    import streamlit as st  # solo lo usa selector_divipola
except Exception:  # pragma: no cover
    st = None

_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "divipola_colombia.json")
_PLACEHOLDER = "Seleccione..."


@lru_cache(maxsize=1)
def cargar_divipola() -> list:
    """Carga el dataset DIVIPOLA (caché en memoria vía lru_cache).
    Devuelve list[dict] con keys: departamento, codigo_dpto, municipio, codigo_mpio."""
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_departamentos() -> list:
    """Nombres de departamento, únicos y ordenados alfabéticamente."""
    return sorted({d["departamento"] for d in cargar_divipola()})


def get_municipios(departamento: str) -> list:
    """Municipios (ordenados) del departamento dado. [] si el departamento no existe."""
    dep = (departamento or "").strip()
    return sorted(d["municipio"] for d in cargar_divipola() if d["departamento"] == dep)


def get_codigos(departamento: str, municipio: str) -> tuple:
    """(codigo_dpto zfill(2), codigo_mpio zfill(5)) del par departamento/municipio.
    Devuelve (None, None) si no se encuentra."""
    dep = (departamento or "").strip()
    mun = (municipio or "").strip()
    for d in cargar_divipola():
        if d["departamento"] == dep and d["municipio"] == mun:
            return (str(d["codigo_dpto"]).zfill(2), str(d["codigo_mpio"]).zfill(5))
    return (None, None)


def selector_divipola(key_prefix: str):
    """Selector encadenado Departamento -> Municipio (muestra NOMBRES, resuelve CÓDIGOS).

    Devuelve (state_code, city_code) con zfill(2)/zfill(5), o (None, None) si aún no hay
    selección completa. El usuario nunca ve los códigos.
    NOTA: solo se define aquí; la integración a la UI de Dash.py es de un paso posterior (P2).
    """
    if st is None:
        raise RuntimeError("selector_divipola requiere streamlit.")

    deps = [_PLACEHOLDER] + get_departamentos()
    dep = st.selectbox("Departamento", deps, index=0, key=f"{key_prefix}_dep")
    if dep == _PLACEHOLDER:
        return (None, None)

    muns = [_PLACEHOLDER] + get_municipios(dep)
    mun = st.selectbox("Municipio", muns, index=0, key=f"{key_prefix}_mun")
    if mun == _PLACEHOLDER:
        return (None, None)

    return get_codigos(dep, mun)
