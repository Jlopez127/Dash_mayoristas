# -*- coding: utf-8 -*-
"""
Created on Mon Jul  7 18:02:55 2025

@author: User
"""

# streamlit_app.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import io
import dropbox
import numpy as np
import re
import unicodedata
import pandas as pd
import math


# 1) Configuración de la página
st.set_page_config(page_title="Dashboard Mayoristas", layout="wide")

# 2) Inicializa Dropbox
cfg_dbx = st.secrets["dropbox"]
dbx = dropbox.Dropbox(
    app_key=cfg_dbx["app_key"],
    app_secret=cfg_dbx["app_secret"],
    oauth2_refresh_token=cfg_dbx["refresh_token"],
)


def get_base_folder() -> str:
    """
    Devuelve la carpeta de Dropbox donde está el Histórico Mayoristas.
    Ej: si remote_path = /Historico mayoristas/Historico mayoristas.xlsx
    retorna: /Historico mayoristas
    """
    remote_path = cfg_dbx["remote_path"].rstrip("/")
    return "/".join(remote_path.split("/")[:-1])



@st.cache_data
def load_data(sheet_name: str) -> pd.DataFrame:
    _, res = dbx.files_download(cfg_dbx["remote_path"])
    df = pd.read_excel(io.BytesIO(res.content), sheet_name=sheet_name)

    # 👇 Caso especial para la hoja COP
    if sheet_name == "1444 - Maria Moises COP":
        if 'Fecha de Carga' not in df.columns and 'Fecha' in df.columns:
            df['Fecha de Carga'] = df['Fecha']  # usar Fecha como Fecha de Carga
    
    if sheet_name != "1444 - Maria Moises" and sheet_name != "1444 - Maria Moises COP":
        df = df.drop(columns=['TRM'], errors='ignore')

    # Normalizaciones
    if 'Fecha de Carga' in df.columns:
        df['Fecha de Carga'] = pd.to_datetime(df['Fecha de Carga'], errors='coerce')
    if 'Fecha' in df.columns:
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    if 'Monto' in df.columns:
        df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce')
    if 'TRM' in df.columns:
        df['TRM'] = pd.to_numeric(df['TRM'], errors='coerce').add(100)

    return df





# === Helpers IngresosConID ===
def _try_download_excel(path: str) -> pd.DataFrame | None:
    try:
        _, res = dbx.files_download(path)
        return pd.read_excel(io.BytesIO(res.content))
    except Exception:
        return None
    
def _norm_colname(s: str) -> str:
    s = str(s)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = s.replace("\u00a0", " ").lower().strip()
    return " ".join(s.split())

def _find_fecha_sistema_col(df: pd.DataFrame) -> str | None:
    norm_map = {_norm_colname(c): c for c in df.columns}
    candidatos = {"fecha de sistema", "fecha sistema", "fecha del sistema", "fechasistema"}
    for t in candidatos:
        if t in norm_map:
            return norm_map[t]
    # contiene ambas palabras
    for nrm, orig in norm_map.items():
        if "fecha" in nrm and "sistema" in nrm:
            return orig
    return None

def _format_dd_mm_yyyy_for_bancos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte la columna 'Fecha de Sistema' (si existe con ese u otro nombre) a string dd-mm-aaaa.
    No convierte a datetime; deja texto. Si no existe, no hace nada.
    """
    col = _find_fecha_sistema_col(df)
    if col is None:
        return df  # no hay columna; salir silencioso

    s = df[col].astype(str).str.strip()
    # deja sólo dígitos y completa a 8: 7102025 -> 07102025
    s8 = s.str.replace(r"[^\d]", "", regex=True).str.zfill(8)
    parsed = pd.to_datetime(s8, format="%d%m%Y", errors="coerce")
    out = parsed.dt.strftime("%d-%m-%Y")
    # donde no se pudo parsear, deja el original
    out = out.where(parsed.notna(), s).astype("string")

    # escribe siempre en la columna estándar
    df["Fecha de Sistema"] = out
    return df

@st.cache_data
def load_ingresos_con_id(casillero: str) -> dict[str, pd.DataFrame]:
    """
    Carga desde Dropbox SOLO los archivos de Ingresos y Clientes
    que correspondan al casillero dado.
    Ejemplos válidos:
        ingresos_1633.xlsx
        ingresos_1633_Bancolombia.xlsx
        ingresos_1633_bancolombia.xlsx
        ingresos_1633_Davivienda.xlsx
        Clientes_1633.xlsx
    """
    base_folder = get_base_folder()
    out: dict[str, pd.DataFrame] = {}

    # 1) Listar archivos en la carpeta del histórico
    try:
        res = dbx.files_list_folder(base_folder)
        entries = res.entries
        while res.has_more:
            res = dbx.files_list_folder_continue(res.cursor)
            entries.extend(res.entries)
    except Exception as e:
        st.error(f"❌ No se pudieron listar archivos de Dropbox: {e}")
        return {}

    import re as _re
    patron_ing = _re.compile(rf"^ingresos_{casillero}(?:_.*)?\.xlsx$", _re.IGNORECASE)
    patron_cli = _re.compile(rf"^clientes_{casillero}\.xlsx$", _re.IGNORECASE)

    for ent in entries:
        # Solo archivos, no carpetas
        if not isinstance(ent, dropbox.files.FileMetadata):
            continue

        name = ent.name  # p.ej. 'ingresos_1633_bancolombia.xlsx'
        fullpath = f"{base_folder}/{name}"

        # ¿Es un archivo de ingresos o de clientes del casillero?
        if not (patron_ing.match(name) or patron_cli.match(name)):
            continue

        df = _try_download_excel(fullpath)
        if df is None or df.empty:
            continue

        # Normaliza columnas clave para TODOS los ingresos/clientes
        for col in ("ID_INGRESO", "Factura", "Id_cliente"):
            if col not in df.columns:
                df[col] = pd.NA

        # Solo a INGRESOS (no Clientes) les aplicamos el formateo de fecha
        if patron_ing.match(name) and ("davivienda" not in name.lower()):
            df = _format_dd_mm_yyyy_for_bancos(df)

        # Evitar duplicados por nombre
        if name not in out:
            out[name] = df

    return out





# 3) Diccionario de claves por hoja
# 3) Diccionario de claves por hoja
PASSWORDS = {
    "clave_nathalia":    "1633 - Nathalia Ospina",
    "clave_maira":       "9444 - Maira Alejandra Paez",
    "clave_jimmy":       "14856 - Jimmy Cortes",
    "clave_elvis":       "11591 - Paula Herrera",
    "clave_maria":       "1444 - Maria Moises",
    "clave_julian":       "13608 - julian sanchez",
    "clave_juan":     "9680 - Juan Felipe Laverde" 
}


# 4) Pedir clave en el sidebar
st.sidebar.title("🔒 Acceso Mayorista")

# 🔄 Botón de refresco manual
if st.sidebar.button("🔄 Refrescar datos"):
    # Limpia cachés
    load_data.clear()
    try:
        load_ingresos_con_id.clear()  # solo si la decoraste con @st.cache_data
    except Exception:
        pass
    st.session_state.pop("ingresos_id_archivos", None)
    st.rerun()

# 🔐 Login
password = st.sidebar.text_input("Introduce tu clave", type="password")
if not password:
    st.sidebar.warning("Debes introducir tu clave para continuar")
    st.stop()
if password not in PASSWORDS:
    st.sidebar.error("Clave incorrecta")
    st.stop()

# 📄 Hoja y datos principales
sheet_name = PASSWORDS[password]
df = load_data(sheet_name)

# 🗂️ Mapeo hoja → casillero para cargar IngresosConID en segundo plano
SHEET_TO_CAS = {
    "1633 - Nathalia Ospina":      "1633",
    "9444 - Maira Alejandra Paez": "9444",
    "14856 - Jimmy Cortes":        "14856",
    "11591 - Paula Herrera":       "11591",
    "1444 - Maria Moises":         "1444",
    "9680 - Juan Felipe Laverde": "9680",
    "13608 - julian sanchez":      "13608",
}
casillero_actual = SHEET_TO_CAS.get(sheet_name)

# 🚚 Carga silenciosa de IngresosConID a sesión (sin renderizar)
if casillero_actual:
    loaded = load_ingresos_con_id(casillero_actual)  # puede venir cacheado
    existing = st.session_state.get("ingresos_id_archivos", {}) or {}
    # Merge: lo que ya esté en sesión (p.ej., Clientes editados) GANA sobre lo cacheado
    merged = {**loaded, **existing}
    st.session_state["ingresos_id_archivos"] = merged
else:
    st.session_state["ingresos_id_archivos"] = {}



# 👉 Solo si es Maria Moises: cargar la hoja en COP adicional
df_cop = None
if sheet_name == "1444 - Maria Moises":
    try:
        df_cop = load_data("1444 - Maria Moises COP")
    except Exception as e:
        st.error(f"⚠️ No se pudo cargar la hoja en COP: {e}")
        
        
st.header(f"📋 Conciliaciones: {sheet_name}")

# 6) Mostrar fecha de última actualización
ultima = df['Fecha de Carga'].max()
st.markdown(f"## Última actualización: **{ultima.strftime('%Y-%m-%d')}**")


st.header("💰 Saldo al cierre de la última actualización")

# Filtra los "Total" de la última fecha de carga
df_tot_ultima = df[
    (df["Tipo"].astype(str).str.strip().str.lower() == "total") &
    (df["Fecha de Carga"] == ultima)
].copy()

if not df_tot_ultima.empty:
    # Asegura numérico y descarta nulos
    df_tot_ultima["Monto"] = pd.to_numeric(df_tot_ultima["Monto"], errors="coerce")
    df_tot_ultima = df_tot_ultima.dropna(subset=["Monto"])

    # Toma el MÁS BAJO; si hay empate, el ÚLTIMO registro
    min_val = df_tot_ultima["Monto"].min()
    fila_elegida = df_tot_ultima.tail(1)

    monto_tot = float(fila_elegida["Monto"].iloc[0])
    color = "green" if monto_tot >= 0 else "red"

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            f"""
            <div style="text-align:center; font-size:3rem; font-weight:bold; color:{color};">
              1️⃣ ${monto_tot:,.0f}
            </div>
            """,
            unsafe_allow_html=True
        )
else:
    st.info("⚠️ No hay registro 'Total' para la última fecha de carga.")



# 7) Filtro por Fecha de Carga
min_fecha = df['Fecha de Carga'].min().date()
start_date = st.sidebar.date_input(
    "Mostrar desde Fecha de Carga",
    value=min_fecha,
    min_value=min_fecha
)
start_date = pd.to_datetime(start_date)
df = df[df['Fecha de Carga'] >= start_date]

# 8) Dashboard

# 8.1️⃣ Ingresos (tabla)
# 8.1️⃣ Ingresos (tabla)
st.markdown("<h3 style='text-align:center;'>2️⃣ Ingresos</h3>", unsafe_allow_html=True)
# 👇 Columnas base
# 👇 Columnas base
cols_in = ['Fecha','Monto','Motivo','Orden','Nombre del producto']
# 👇 Agrega TRM SOLO para '1444 - Maria Moises' si está disponible
if sheet_name == "1444 - Maria Moises" and 'TRM' in df.columns:
    cols_in.append('TRM')

df_in = df.loc[df['Tipo'] == 'Ingreso', cols_in].copy()

if df_in.empty:
    st.info("Aún no hay ingresos para mostrar.")
else:
    # --- Reglas de Motivo ---
    np_nombre = df_in['Nombre del producto'].astype(str).str.strip().str.upper()
    np_motivo = (
        df_in['Motivo']
        .astype(str).fillna('')
        .str.strip()
        .str.replace(r'\s+', ' ', regex=True)
        .str.replace('-', '_')
        .str.replace(' ', '_')
        .str.upper()
    )
    is_devolucion = np_nombre.isin(['TOTAL', 'PARCIAL'])
    is_ingreso_extra = np_motivo.isin(['INGRESO_EXTRA', 'INGRESOS_EXTRA'])

    df_in.loc[is_devolucion, 'Motivo'] = 'Devolucion'
    df_in.loc[~is_devolucion & is_ingreso_extra, 'Motivo'] = 'Ingreso_extra'
    df_in.loc[~is_devolucion & ~is_ingreso_extra, 'Motivo'] = 'Consignacion cuenta propia'

    # Tipos y limpieza
    df_in['Fecha'] = pd.to_datetime(df_in['Fecha'], errors='coerce')
    df_in['Monto'] = pd.to_numeric(df_in['Monto'], errors='coerce')

    # 👉 Solo Maria Moises: agregar columna Monto COP
    if sheet_name == "1444 - Maria Moises" and 'TRM' in df_in.columns:
        df_in['Monto COP'] = df_in['Monto'] * df_in['TRM']

    df_in = df_in[df_in['Monto'].notna() & df_in['Monto'].ne(0)]

    # Vaciar 'Orden'
    motivo_norm = (
        df_in['Motivo'].astype(str).fillna('')
        .str.strip()
        .str.replace(r'\s+', ' ', regex=True)
        .str.replace('-', '_')
        .str.replace(' ', '_')
        .str.upper()
    )
    mask_vaciar_orden = motivo_norm.isin(['INGRESO_EXTRA', 'CONSIGNACION_CUENTA_PROPIA'])
    df_in.loc[mask_vaciar_orden, 'Orden'] = ''

    # Ordenar para la vista
    df_in = df_in.sort_values('Fecha', ascending=False, na_position='last')

    # === Exportación ===
    df_export = df_in.copy()
    df_export['Fecha'] = pd.to_datetime(df_export['Fecha'], errors='coerce').dt.date

    # === Mostrar formateado ===
    df_in['Fecha'] = pd.to_datetime(df_in['Fecha'], errors='coerce').dt.strftime('%Y-%m-%d')
    df_in['Monto'] = pd.to_numeric(df_in['Monto'], errors='coerce').map(lambda x: f"${x:,.0f}")
    if 'Monto COP' in df_in.columns:
        df_in['Monto COP'] = pd.to_numeric(df_in['Monto COP'], errors='coerce').map(lambda x: f"${x:,.0f}")
    st.dataframe(df_in, use_container_width=True)

    # === Botón descarga ===
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="Ingresos")
    buf.seek(0)

    c1, c2, c3 = st.columns([4, 2, 4])
    with c2:
        st.download_button(
            label="📥 Descargar Ingresos",
            data=buf.getvalue(),
            file_name=f"Ingresos_{sheet_name.split(' - ')[0]}_{ultima.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# 8.2️⃣ Compras realizadas (Egresos) (tabla)
# 8.2️⃣ Compras realizadas (Egresos)
st.markdown("<h3 style='text-align:center;'>3️⃣ Compras realizadas (Egresos)</h3>", unsafe_allow_html=True)
df_eg = df.loc[df['Tipo'] == 'Egreso', ['Fecha','Orden','Monto','Nombre del producto']].copy()

if df_eg.empty:
    st.info("Aún no hay compras registradas.")
else:
    # Tipos y ordenamiento
    df_eg['Fecha'] = pd.to_datetime(df_eg['Fecha'], errors='coerce')
    df_eg['Monto'] = pd.to_numeric(df_eg['Monto'], errors='coerce')
    df_eg = df_eg.sort_values('Fecha', ascending=False, na_position='last')

    # === Preparar exportación (sin formatos de pantalla) ===
    df_eg_export = df_eg.copy()
    df_eg_export['Fecha'] = df_eg_export['Fecha'].dt.date  # fecha limpia para Excel

    # === Mostrar tabla formateada en UI ===
    df_eg['Fecha'] = df_eg['Fecha'].dt.strftime('%Y-%m-%d')
    df_eg['Monto'] = df_eg['Monto'].map(lambda x: f"${x:,.0f}")
    st.dataframe(df_eg, use_container_width=True)

    # === Botón de descarga compacto y centrado ===
    buf_eg = io.BytesIO()
    with pd.ExcelWriter(buf_eg, engine="openpyxl") as writer:
        df_eg_export.to_excel(writer, index=False, sheet_name="Egresos")
    buf_eg.seek(0)

    c1, c2, c3 = st.columns([4, 2, 4])
    with c2:
        st.download_button(
            label="📥 Descargar Egresos",
            data=buf_eg.getvalue(),
            file_name=f"Egresos_{sheet_name.split(' - ')[0]}_{ultima.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True  # ocupa solo la columna central (estrecha)
        )


st.markdown("<h3 style='text-align:center;'>🧾 Consolidado (Ingresos + Egresos)</h3>", unsafe_allow_html=True)

# Copias para consolidado (pueden venir ya formateadas para UI)
df_in_c = df_in.copy()
df_eg_c = df_eg.copy()

df_in_c['Tipo'] = 'Ingreso'

df_eg_c['Tipo'] = 'Egreso'

df_consol = pd.concat([df_in_c, df_eg_c], ignore_index=True)

# Ordenar por Fecha (más reciente arriba)
df_consol = df_consol.sort_values('Fecha', ascending=False, na_position='last')

# Export: Fecha como date (no string), sin formatos de moneda
df_consol_exp = df_consol.copy()
df_consol_exp['Fecha'] = pd.to_datetime(df_consol_exp['Fecha'], errors='coerce').dt.date

# Botón compacto y centrado
buf_cons = io.BytesIO()
with pd.ExcelWriter(buf_cons, engine="openpyxl") as writer:
    df_consol_exp.to_excel(writer, index=False, sheet_name="Consolidado")
buf_cons.seek(0)

c1, c2, c3 = st.columns([4, 2, 4])
with c2:
    st.download_button(
        label="📦 Descargar consolidado completo",
        data=buf_cons.getvalue(),
        file_name=f"Consolidado_{sheet_name.split(' - ')[0]}_{ultima.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )






## EGRESOS EN COP MARIA MOPISES




# 👉 Crear df_eg_extra_cop solo para Maria Moises
df_eg_extra_cop = None
if sheet_name == "1444 - Maria Moises" and df_cop is not None:
    try:
        # Filtrar solo las columnas necesarias
        cols_needed = ['Fecha', 'Egreso_extra_COP', 'GMF_4x1000_COP']
        df_eg_extra_cop = df_cop[cols_needed].copy()

        # Asegurar tipos
        df_eg_extra_cop['Fecha'] = pd.to_datetime(df_eg_extra_cop['Fecha'], errors='coerce')
        df_eg_extra_cop = df_eg_extra_cop.dropna(subset=['Fecha'])

        # Ordenar por fecha descendente
        df_eg_extra_cop = df_eg_extra_cop.sort_values('Fecha', ascending=False)

        # Mostrar en UI
        st.markdown("<h3 style='text-align:center;'>🪙 Egresos Extra en COP</h3>", unsafe_allow_html=True)
        df_tmp = df_eg_extra_cop.copy()
        df_tmp['Fecha'] = df_tmp['Fecha'].dt.strftime('%Y-%m-%d')
        df_tmp['Egreso_extra_COP'] = pd.to_numeric(df_tmp['Egreso_extra_COP'], errors='coerce').map(lambda x: f"${x:,.0f}")
        df_tmp['GMF_4x1000_COP'] = pd.to_numeric(df_tmp['GMF_4x1000_COP'], errors='coerce').map(lambda x: f"${x:,.0f}")
        st.dataframe(df_tmp, use_container_width=True)

        # Exportar a Excel
        buf_extra = io.BytesIO()
        with pd.ExcelWriter(buf_extra, engine="openpyxl") as writer:
            df_eg_extra_cop.to_excel(writer, index=False, sheet_name="EgresosExtraCOP")
        buf_extra.seek(0)

        c1, c2, c3 = st.columns([4, 2, 4])
        with c2:
            st.download_button(
                label="📥 Descargar Egresos Extra COP",
                data=buf_extra.getvalue(),
                file_name=f"EgresosExtraCOP_{ultima.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    except Exception as e:
        st.error(f"⚠️ Error procesando Egresos Extra COP: {e}")




############################################ FACTURACION##############################################################





############################################ FACTURACIÓN — CLIENTES ################################################
############################################ FACTURACIÓN ############################################################
# Carga silenciosa de la base "Clientes" para el casillero actual y UI:
# Orden visual: 1) Filtro  2) Agregar cliente  3) Ver tabla
# ========================= FACTURACIÓN — CLIENTES =========================

# ✅ Casilleros habilitados para facturación
FACT_CAS_ALLOW = {"9680", "13608", "1633", "1444"}

st.subheader("📇 Facturación — Clientes")

# ⛔ Bloqueo total si no aplica facturación
if casillero_actual not in FACT_CAS_ALLOW:
    st.info("📌 El módulo de facturación solo está disponible para 9680, 13608, 1633 y 1444.")
    st.stop()

# -------------------- A PARTIR DE AQUÍ FACTURACIÓN ACTIVA --------------------

df_clientes: pd.DataFrame | None = None

if not casillero_actual:
    st.error("No se pudo identificar el casillero actual para facturación.")
    st.stop()

# 1) Buscar en memoria (ej.: Clientes_1633.xlsx)
ingresos_id_archivos = st.session_state.get("ingresos_id_archivos", {}) or {}
key_clientes = next(
    (
        k for k in ingresos_id_archivos.keys()
        if k.lower().startswith("clientes_")
        and k.split("_")[-1].split(".")[0] == str(casillero_actual)
    ),
    None
)

if key_clientes:
    df_clientes = ingresos_id_archivos[key_clientes].copy()

# 2) Si no estaba en memoria, descargar de Dropbox
if df_clientes is None:
    base_folder = get_base_folder()
    for _path in (
        f"{base_folder}/Clientes_{casillero_actual}.xlsx",
        f"{base_folder}/clientes_{casillero_actual}.xlsx",
    ):
        _df = _try_download_excel(_path)
        if _df is not None and not _df.empty:
            df_clientes = _df.copy()
            break
        
# --- Constantes de columnas (usa exactamente estos nombres en el archivo) ---
COL_ID   = "Identificación (Obligatorio)"
COL_NOM  = "Nombres del tercero (Obligatorio)"
COL_APE  = "Apellidos del tercero (Obligatorio)"
COL_DIR  = "Dirección"
COL_DEP  = "Código departamento/estado"
COL_CIU  = "Código ciudad"
COL_TEL  = "Teléfono principal"
COL_MAIL = "Correo electrónico contacto principal"

REQUIRED_COLS = [COL_ID, COL_NOM, COL_APE, COL_DIR, COL_DEP, COL_CIU, COL_TEL, COL_MAIL]

# Defaults y derivadas
DEFAULTS_STATIC = {
    "Tipo identificación": "13",
    "Tipo (Obligatorio)": "Es persona",
    "Código pais": "Col",
    "Tipo de régimen IVA": "0",
    "Código Responsabilidad fiscal": "R-99-PN",
    "Identificación del vendedor": "901408468",
    "Clientes": "SI",
    "Estado": "Activo",
}
DERIVED_FROM_NAME = {
    "Nombres contacto principal": COL_NOM,
    "Apellidos contacto principal": COL_APE,
    "Teléfono contacto principal": COL_TEL,
}

# --- Asegurar df_clientes y columnas mínimas ---
# --- Asegurar df_clientes y columnas mínimas ---
if df_clientes is None or df_clientes.empty:
    all_cols = list({*REQUIRED_COLS, *DEFAULTS_STATIC.keys(), *DERIVED_FROM_NAME.keys()})
    df_clientes = pd.DataFrame(columns=all_cols)
else:
    for c in REQUIRED_COLS:
        if c not in df_clientes.columns:
            df_clientes[c] = pd.NA
    for c in DEFAULTS_STATIC.keys():
        if c not in df_clientes.columns:
            df_clientes[c] = pd.NA
    for c in DERIVED_FROM_NAME.keys():
        if c not in df_clientes.columns:
            df_clientes[c] = pd.NA

# 🔒 Forzar columnas sensibles como STRING (para no perder ceros a la izquierda)
COLS_STR_CRITICAS = [
    COL_DEP,   # Código departamento/estado
    COL_CIU,   # Código ciudad
    COL_TEL,   # Teléfono principal
]

for c in COLS_STR_CRITICAS:
    if c in df_clientes.columns:
        df_clientes[c] = (
            df_clientes[c]
            .astype("string")
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )

# === Normalización de IDs ===
def norm_id(s: object) -> str:
    """ID como string sin espacios, puntos, guiones ni '+'. Conserva ceros."""
    s = "" if s is None else str(s).strip()
    return re.sub(r"[ \.\-\+]", "", s)

df_clientes[COL_ID] = df_clientes[COL_ID].astype("string")
df_clientes["_id_norm"] = df_clientes[COL_ID].map(norm_id).astype("string")

# Completar defaults/derivadas SIN pisar datos existentes (solo donde haya ID)
mask_tiene_id = df_clientes[COL_ID].notna() & df_clientes[COL_ID].astype(str).str.strip().ne("")
for col, val in DEFAULTS_STATIC.items():
    df_clientes.loc[mask_tiene_id, col] = df_clientes.loc[mask_tiene_id, col].fillna(val)
for col_out, col_src in DERIVED_FROM_NAME.items():
    df_clientes.loc[mask_tiene_id, col_out] = df_clientes.loc[mask_tiene_id, col_out].fillna(df_clientes[col_src])

# Ruta de guardado
# Ruta de guardado
base_folder = get_base_folder()
clientes_path = f"{base_folder}/Clientes_{casillero_actual}.xlsx" if casillero_actual else None


def _save_clientes_to_dropbox(df_to_save: pd.DataFrame) -> bool:
    """Guarda el DF de clientes en Dropbox."""
    try:
        buf_cli = io.BytesIO()
        with pd.ExcelWriter(buf_cli, engine="openpyxl") as w:
            # Ordena: primero requeridas, luego el resto
            cols_exist = [c for c in REQUIRED_COLS if c in df_to_save.columns]
            cols_rest  = [c for c in df_to_save.columns if c not in cols_exist]
            df_to_save[cols_exist + cols_rest].to_excel(w, index=False, sheet_name="Clientes")
        buf_cli.seek(0)
        dbx.files_upload(buf_cli.read(), clientes_path, mode=dropbox.files.WriteMode.overwrite)
        return True
    except Exception as e:
        st.error(f"❌ No se pudo guardar el archivo de clientes: {e}")
        return False

# ======================= (1) Filtro por Identificación =======================
with st.container(border=True):
    st.markdown("**Buscar cliente por Identificación**")
    filt_id = st.text_input(
        "Identificación",
        key="cli_filter_id",
        placeholder="Escribe una identificación (coincidencias parciales)"
    )

# ======================= (2) Alta de nuevo cliente ===========================
with st.container(border=True):
    st.markdown("**¿Deseas agregar un nuevo cliente?**")
    add_choice = st.radio("Selecciona una opción:", ["No", "Sí"], horizontal=True, index=0, key="cli_add_choice")

    if add_choice == "Sí":
        c1, c2 = st.columns(2)
        with c1:
            new_id  = st.text_input(COL_ID,  key="cli_new_id",  placeholder="Ej: 123456789")
            new_nom = st.text_input(COL_NOM, key="cli_new_nom", placeholder="Nombres")
            new_dir = st.text_input(COL_DIR, key="cli_new_dir", placeholder="Calle 123 #45-67")
            new_tel = st.text_input(COL_TEL, key="cli_new_tel", placeholder="Solo dígitos")
        with c2:
            new_ape  = st.text_input(COL_APE,  key="cli_new_ape",  placeholder="Apellidos")
            new_dep  = st.text_input(COL_DEP,  key="cli_new_dep",  placeholder="Código Dpto/Estado")
            new_ciu  = st.text_input(COL_CIU,  key="cli_new_ciu",  placeholder="Código Ciudad")
            new_mail = st.text_input(COL_MAIL, key="cli_new_mail", placeholder="correo@dominio.com")

        if st.button("💾 Guardar cliente", use_container_width=True):
            # Validaciones obligatorias
            values = {
                COL_ID: new_id, COL_NOM: new_nom, COL_APE: new_ape, COL_DIR: new_dir,
                COL_DEP: new_dep, COL_CIU: new_ciu, COL_TEL: new_tel, COL_MAIL: new_mail
            }
            faltan = [k for k, v in values.items() if not str(v).strip()]
            if faltan:
                st.error("Por favor completa todos los campos requeridos.")
            else:
                # Validar email
                email_ok = re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(new_mail).strip()) is not None
                if not email_ok:
                    st.error("El correo no parece válido.")
                else:
                    # Tel: solo dígitos 6–20
                    tel_norm = re.sub(r"\D", "", str(new_tel))
                    tel_ok = re.match(r"^\d{6,20}$", tel_norm) is not None
                    if not tel_ok:
                        st.error("El teléfono debe contener solo dígitos (6 a 20).")
                    else:
                        # Duplicado por Identificación exacta (normalizada y cruda)
                        raw_eq = df_clientes[COL_ID].astype(str).str.strip().eq(str(new_id).strip()).any()
                        norm_eq = df_clientes["_id_norm"].astype(str).str.strip().eq(norm_id(new_id)).any()
                        if raw_eq or norm_eq:
                            st.error("Ya existe un cliente con esa Identificación.")
                        else:
                            nueva = {
                                COL_ID: str(new_id).strip(),
                                COL_NOM: str(new_nom).strip(),
                                COL_APE: str(new_ape).strip(),
                                COL_DIR: str(new_dir).strip(),
                                COL_DEP: str(new_dep).strip(),
                                COL_CIU: str(new_ciu).strip(),
                                COL_TEL: tel_norm,
                                COL_MAIL: str(new_mail).strip(),
                                # defaults estáticos
                                **{k: DEFAULTS_STATIC[k] for k in DEFAULTS_STATIC},
                                # derivados
                                "Nombres contacto principal": str(new_nom).strip(),
                                "Apellidos contacto principal": str(new_ape).strip(),
                                "Teléfono contacto principal": tel_norm,
                            }

                            # Asegurar tipos de texto para no perder ceros a la izquierda
                            df_clientes[COL_ID] = df_clientes[COL_ID].astype("string")
                            df_clientes[COL_TEL] = df_clientes[COL_TEL].astype("string")

                            df_clientes = pd.concat([df_clientes, pd.DataFrame([nueva])], ignore_index=True)

                            # Recalcular normalización
                            df_clientes[COL_ID] = df_clientes[COL_ID].astype("string")
                            df_clientes["_id_norm"] = df_clientes[COL_ID].map(norm_id).astype("string")

                            # Guardar en Dropbox
                            ok = _save_clientes_to_dropbox(df_clientes)
                            if ok:
                                # Actualizar sesión con la versión más reciente
                                silent = st.session_state.get("ingresos_id_archivos", {}) or {}
                                silent[f"Clientes_{casillero_actual}.xlsx"] = df_clientes.copy()
                                st.session_state["ingresos_id_archivos"] = silent
                                try:
                                    load_ingresos_con_id.clear()  # limpiar caché de la carga silenciosa
                                except Exception:
                                    pass
                                st.success("✅ Cliente guardado correctamente.")
                                st.rerun()

# ======================= (3) Ver tabla (aplicando filtro) ====================
# Toma siempre lo último desde session_state (post-guardado)
ing_sess = st.session_state.get("ingresos_id_archivos", {}) or {}
df_clientes = ing_sess.get(f"Clientes_{casillero_actual}.xlsx", df_clientes)

if df_clientes is None:
    df_clientes = pd.DataFrame(columns=REQUIRED_COLS)

with st.container():
    if 'filt_id' in locals() and filt_id:
        mask = (
            df_clientes[COL_ID]
            .astype(str).str.strip()
            .str.contains(str(filt_id).strip(), case=False, na=False)
        )
        df_mostrar = df_clientes.loc[mask].copy()
        if df_mostrar.empty:
            st.info("No existe cliente con ese ID.")
        else:
            st.dataframe(df_mostrar, use_container_width=True)
    else:
        st.dataframe(df_clientes, use_container_width=True)
# ===================== /FACTURACIÓN — CLIENTES =====================

############################################ /FACTURACIÓN 2!! ###########################################################

        

# === FACTURACIÓN — Vista de Ingresos con ID (general + Davivienda 1444) ===
# === FACTURACIÓN — Vista de Ingresos con ID (general + Davivienda 1444) ===
# === FACTURACIÓN — Vista de Ingresos con ID (general + Davivienda 1444) ===
# =========================
# FACTURACIÓN — Asignar ID_cliente a Ingresos
# =========================
# ================================
# 🧾 Editar ID_cliente en IngresosConID
# ================================
st.subheader("🧾 Ingresos con ID — Asignar/Editar ID_cliente")

# 1) Tomar archivos de IngresosConID desde la sesión (excluyendo Clientes_*.xlsx)
ing_arch = st.session_state.get("ingresos_id_archivos", {}) or {}
ing_keys = [k for k in ing_arch.keys() if not k.lower().startswith("clientes_")]

if not ing_keys:
    st.info("No hay archivos de IngresosConID para este casillero.")
else:
    # Sugerir Bancolombia para 1444
    default_idx = 0
    if casillero_actual == "1444":
        for i, k in enumerate(ing_keys):
            if "bancolombia" in k.lower():
                default_idx = i
                break

    fname_sel = st.selectbox("Selecciona el archivo a trabajar", options=ing_keys, index=default_idx)
    df_ing_id = ing_arch.get(fname_sel, pd.DataFrame()).copy()

    # Asegurar columnas mínimas
    for c in ("IDMovimiento", "Id_cliente"):
        if c not in df_ing_id.columns:
            df_ing_id[c] = pd.NA

    # (Para mapear de vuelta) conservar índice original
    df_ing_id["__rowid"] = df_ing_id.index

    # -----------------------------------------------------------------------
    # FILTRO: excluir valores negativos y "ABONO INTERESES AHORROS"
    # -----------------------------------------------------------------------
    amount_cols = [c for c in ["Valor", "VALOR", "Valor Total", "Monto"] if c in df_ing_id.columns]
    if amount_cols:
        for c in amount_cols:
            df_ing_id[c] = pd.to_numeric(df_ing_id[c], errors="coerce")
        any_negative = (df_ing_id[amount_cols] < 0).any(axis=1)
    else:
        any_negative = pd.Series(False, index=df_ing_id.index)

    ref_cols = [c for c in [
        "REFERENCIA", "Referencia 1", "Referencia 2",
        "Descripción", "Descripcion", "Descripcion Motivo"
    ] if c in df_ing_id.columns]

    if ref_cols:
        ref_mask = pd.Series(True, index=df_ing_id.index)
        for c in ref_cols:
            col_upper = df_ing_id[c].astype(str).str.strip().str.upper()
            ref_mask &= ~col_upper.eq("ABONO INTERESES AHORROS")
    else:
        ref_mask = pd.Series(True, index=df_ing_id.index)

    df_ing_id = df_ing_id[~any_negative & ref_mask].copy()
    # -----------------------------------------------------------------------
    # Asegurar columna Fecha de Sistema y completarla desde IDMovimiento si falta
    # Asegurar columna
    if "Fecha de Sistema" not in df_ing_id.columns:
        df_ing_id["Fecha de Sistema"] = pd.NA
    
    # Considerar como “vacío” estos textos además de NaN
    _vacios_txt = {"", "nan", "none", "null", "na"}
    mask_missing_sysdate = (
        df_ing_id["Fecha de Sistema"].isna() |
        df_ing_id["Fecha de Sistema"].astype(str).str.strip().str.lower().isin(_vacios_txt)
    )
    
    # Rellenar con los primeros 10 caracteres del IDMovimiento (ej. '2025-10-08')
    df_ing_id.loc[mask_missing_sysdate, "Fecha de Sistema"] = (
        df_ing_id["ID_INGRESO"].astype(str).str.slice(0, 10)
    )
    
    # 2) Columnas a visualizar (mostramos las que existan tal cual)
    cols_preferencia = [
        "ID_INGRESO", "Id_cliente", "Factura",
        "Fecha de Sistema", "Fecha",
        "Descripción", "Descripcion Motivo",
        "Documento", "Transaccion", "Oficina de Recaudo", "ID Origen/Destino",
        "REFERENCIA", "Referencia 1", "Referencia 2",
        "Valor", "VALOR", "Valor Total", "Monto",
        "Nombre del producto",
    ]
    cols_presentes = [c for c in cols_preferencia if c in df_ing_id.columns]
    cols_mostrar = ["__rowid"] + cols_presentes
    
    df_view = df_ing_id[cols_mostrar].copy()

    # 3) Columna editable para el ID de cliente
    df_view["Nuevo_ID_cliente"] = df_ing_id["Id_cliente"].astype("string").fillna("")

    # Set de IDs válidos en Clientes
    COL_ID = "Identificación (Obligatorio)"
    ids_validos = set()
    if df_clientes is not None and not df_clientes.empty and COL_ID in df_clientes.columns:
        ids_validos = set(df_clientes[COL_ID].astype(str).str.strip().dropna().unique().tolist())

    from streamlit import column_config
    colconf = {"__rowid": column_config.Column(disabled=True, label="")}
    for c in cols_presentes:
        colconf[c] = column_config.Column(disabled=True)
    colconf["Nuevo_ID_cliente"] = column_config.TextColumn(help="Debe existir en Clientes.")

    df_edit = st.data_editor(
        df_view,
        use_container_width=True,
        key="ed_ing_id",
        column_config=colconf,
        hide_index=True
    )

    # 5) Guardar
    if st.button("💾 Guardar cambios en ID_cliente", use_container_width=True):
        if not ids_validos:
            st.error("La base de Clientes no está disponible o no tiene 'Identificación (Obligatorio)'. Crea clientes primero.")
        else:
            df_apply = df_edit[["__rowid", "Nuevo_ID_cliente"]].copy()
            df_apply["Nuevo_ID_cliente"] = df_apply["Nuevo_ID_cliente"].astype(str).str.strip()

            df_current = df_ing_id.set_index("__rowid")["Id_cliente"].astype(str).str.strip()
            changed_mask = df_apply.apply(
                lambda r: str(df_current.get(r["__rowid"], "") or "") != (r["Nuevo_ID_cliente"] or ""),
                axis=1
            )
            df_apply = df_apply[changed_mask]

            if df_apply.empty:
                st.info("No hay cambios para guardar.")
            else:
                df_nonempty = df_apply[df_apply["Nuevo_ID_cliente"].ne("")]
                ids_no_existen = sorted({i for i in df_nonempty["Nuevo_ID_cliente"].tolist() if i not in ids_validos})
                if ids_no_existen:
                    st.error(
                        "Estos ID(s) NO existen en Clientes. Debes crearlos primero:\n- "
                        + "\n- ".join(ids_no_existen[:30])
                        + ("..." if len(ids_no_existen) > 30 else "")
                    )
                else:
                    for _, r in df_apply.iterrows():
                        rid = r["__rowid"]
                        nuevo = r["Nuevo_ID_cliente"]
                        df_ing_id.loc[df_ing_id["__rowid"] == rid, "Id_cliente"] = nuevo

                    # 👇 USAR SIEMPRE LA MISMA CARPETA DEL HISTÓRICO
                    base_folder = get_base_folder()
                    fullpath = f"{base_folder}/{fname_sel}"
                    try:
                        to_save = df_ing_id.drop(columns=["__rowid"], errors="ignore")
                        buf = io.BytesIO()
                        with pd.ExcelWriter(buf, engine="openpyxl") as w:
                            to_save.to_excel(w, index=False, sheet_name="Ingresos")
                        buf.seek(0)
                        dbx.files_upload(buf.read(), fullpath, mode=dropbox.files.WriteMode.overwrite)
                    except Exception as e:
                        st.error(f"❌ No se pudo guardar el archivo en Dropbox: {e}")
                    else:
                        ing_arch[fname_sel] = df_ing_id.copy()
                        st.session_state["ingresos_id_archivos"] = ing_arch
                        try:
                            load_ingresos_con_id.clear()
                        except Exception:
                            pass
                        st.success("✅ Cambios guardados en el archivo de IngresosConID.")
                        st.rerun()




################################################ FACTRURACION MODULO 3 ############################################################




# ———— FACTURACIÓN: LEFT JOIN (Ingresos ⭠ Clientes) y exportar ————
# ———— FACTURACIÓN: LEFT JOIN (Ingresos ⭠ Clientes) y exportar ————


# ———— FACTURACIÓN: Preparar base (leer última versión y filtrar pendientes) ————
st.divider()
st.subheader("🧾 Generar facturación")

if st.button("Preparar facturación", use_container_width=True):
    COL_ID = "Identificación (Obligatorio)"

    if not casillero_actual:
        st.error("No se pudo identificar el casillero actual.")
    else:
        try:
            # 1️⃣ Refrescar SIEMPRE la última versión desde Dropbox
            try:
                load_ingresos_con_id.clear()
            except Exception:
                pass

            ingresos_dict = load_ingresos_con_id(casillero_actual)  # SOLO archivos del casillero actual

            # 🔹 Separar ingresos vs clientes
            ingresos_dfs = {
                name: df for name, df in ingresos_dict.items()
                if not name.lower().startswith("clientes_")
            }

            clientes_df = None
            for name, df in ingresos_dict.items():
                if name.lower().startswith("clientes_"):
                    # 👉 AQUÍ cargamos clientes COMPLETOS, SIN FILTROS
                    clientes_df = df.copy()
                    break  # solo uno por casillero

            # Backup por si no lo encontró en ingresos_dict
            if clientes_df is None:
                base_folder = get_base_folder()
                for _path in (
                    f"{base_folder}/Clientes_{casillero_actual}.xlsx",
                    f"{base_folder}/clientes_{casillero_actual}.xlsx",
                ):
                    _df_cli = _try_download_excel(_path)
                    if _df_cli is not None:
                        clientes_df = _df_cli.copy()
                        break

            if not ingresos_dfs:
                st.error("No hay archivos de ingresos para este casillero.")
            elif clientes_df is None or clientes_df.empty or COL_ID not in clientes_df.columns:
                st.error("No se encontró la base de Clientes o no tiene la columna 'Identificación (Obligatorio)'.")
            else:
                # 2️⃣ Unir TODOS los ingresos del casillero en un solo DF
                df_ing_list = []
                for name, df_i in ingresos_dfs.items():
                    tmp = df_i.copy()
                    tmp["__source_file"] = name
                    df_ing_list.append(tmp)

                df_ing_full = pd.concat(df_ing_list, ignore_index=True)

                # Asegurar columnas clave en ingresos
                for c in ("Id_cliente", "Factura"):
                    if c not in df_ing_full.columns:
                        df_ing_full[c] = pd.NA

                # 3️⃣ Filtro SOLO SOBRE INGRESOS:
                #     - Id_cliente con valor
                #     - Factura vacía
                id_ok = (
                    df_ing_full["Id_cliente"]
                    .astype(str).str.strip()
                    .ne("") &
                    df_ing_full["Id_cliente"].notna()
                )
                fact_vacia = (
                    df_ing_full["Factura"].isna() |
                    df_ing_full["Factura"].astype(str).str.strip().eq("")
                )
                df_pend = df_ing_full[id_ok & fact_vacia].copy()

                # 4️⃣ Guardar en sesión:
                #     - df_pend: ingresos PENDIENTES de facturar
                #     - clientes_df: TODOS los clientes del casillero
                st.session_state["facturacion_ingresos_pendientes"] = df_pend
                st.session_state["facturacion_clientes_actual"] = clientes_df

                total_ing = len(df_ing_full)
                total_pend = len(df_pend)
                st.success(
                    f"✅ Base de facturación preparada para el casillero {casillero_actual}.\n"
                    f"- Ingresos totales leídos: {total_ing}\n"
                    f"- Ingresos con Id_cliente y Factura vacía: {total_pend}"
                )

                if total_pend > 0:
                    st.markdown("Vista rápida de los ingresos pendientes:")
                    st.dataframe(df_pend.head(50), use_container_width=True)

        except Exception as e:
            st.error(f"❌ Error al preparar la base de facturación: {e}")








import requests
import json
from datetime import datetime





# ======================= FUNCIONES SIIGO UNIFICADAS =======================

def obtain_token():
    """
    Obtiene un token de acceso de la API de Siigo.
    ⚠️ Deja username y access_key vacíos o ponlos en secrets, pero NO hardcodees el token.
    """
    API_URL = "https://api.siigo.com/auth"
    NOMBRE_DE_MI_APP = "AutomatizacionFacturasEncargomio"
    
    # 👉 OPCIÓN 1: Dejar quemado (luego tú lo llenas):
    #credentials = {
     #   "username": "contacto@encargomio.com",
      #  "access_key": "ZDlhZTFiZTUtY2Q3Mi00ODE0LTliZTUtMjU3ZTQ4OGY3MTJlOmN1PnhBOSg4Y04="
    #}

    # 👉 OPCIÓN 2 (recomendada): usar st.secrets (descomenta y configura en Streamlit Cloud)
    credentials = {
         "username": st.secrets["siigo"]["username"],
         "access_key": st.secrets["siigo"]["access_key"],
     }

    headers = {
        "Content-Type": "application/json",
        "Partner-Id": NOMBRE_DE_MI_APP
    }

    try:
        response = requests.post(API_URL, data=json.dumps(credentials), headers=headers)
        
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            print(f"ERROR: La respuesta de autenticación no es un JSON válido. Código: {response.status_code}")
            print(f"Contenido de la respuesta: {response.text[:200]}")
            return None
        
        if response.status_code == 200:
            token = response_data.get('access_token')
            if token:
                print("Token de acceso obtenido exitosamente.")
                return token
            else:
                print("ERROR: No se encontró 'access_token' en la respuesta.")
                print(json.dumps(response_data, indent=2, ensure_ascii=False))
                return None
        else:
            print(f"ERROR al obtener el token (Código: {response.status_code}).")
            print("Respuesta del servidor:")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            return None
            
    except requests.exceptions.Timeout:
        print("ERROR: Tiempo de espera agotado al conectar con la API de Siigo.")
        return None
    except requests.exceptions.ConnectionError:
        print("ERROR: No se pudo establecer conexión con la API de Siigo.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR de conexión: {e}")
        return None
    except Exception as e:
        print(f"ERROR inesperado al obtener token: {e}")
        return None    


def verify_customer(access_token: str, customer_identification: str) -> bool:
    """
    Verifica si existe un cliente en Siigo por su identificación.
    """
    API_CUSTOMERS_URL = "https://api.siigo.com/v1/customers?identification=" + customer_identification

    if not access_token or access_token == "TU_ACCESS_TOKEN":
        print("¡ERROR! Token de acceso inválido.")
        return False

    NOMBRE_DE_MI_APP = "AutomatizacionFacturasEncargomio"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Partner-Id": NOMBRE_DE_MI_APP
    }

    try:
        response = requests.get(API_CUSTOMERS_URL, headers=headers)
        
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            print(f"ERROR: La respuesta no es un JSON válido. Código: {response.status_code}")
            print(f"Contenido de la respuesta: {response.text[:200]}")
            return False

        if response.status_code == 200:
            if 'results' in response_data and len(response_data['results']) >= 1:
                print(f"Cliente con identificación {customer_identification} encontrado.")
                return True
            else:
                print(f"Cliente con identificación {customer_identification} no encontrado.")
                return False
        else:
            print(f"ERROR al verificar el cliente (Código: {response.status_code}).")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            return False
            
    except requests.exceptions.Timeout:
        print("ERROR: Tiempo de espera agotado al conectar con la API de Siigo.")
        return False
    except requests.exceptions.ConnectionError:
        print("ERROR: No se pudo establecer conexión con la API de Siigo.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"ERROR de conexión: {e}")
        return False
    except Exception as e:
        print(f"ERROR inesperado al verificar cliente: {e}")
        return False


def create_customer_siigo(access_token: str, customer_data: dict) -> bool:
    """
    Crea un cliente en Siigo.
    """
    API_URL_CUSTOMERS = "https://api.siigo.com/v1/customers"
    NOMBRE_DE_MI_APP = "AutomatizacionFacturasEncargomio"

    if not access_token or access_token == "TU_ACCESS_TOKEN":
        print("ERROR: Token de acceso inválido.")
        return False

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Partner-Id": NOMBRE_DE_MI_APP
    }

    try:
        response = requests.post(API_URL_CUSTOMERS, data=json.dumps(customer_data), headers=headers)
        
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            print(f"ERROR: La respuesta no es un JSON válido. Código: {response.status_code}")
            print(f"Contenido de la respuesta: {response.text[:200]}")
            return False

        if response.status_code == 201:
            print("¡ÉXITO! Cliente creado correctamente.")
            print(f"  ID del cliente creado: {response_data.get('id')}")
            return True
        else:
            print(f"ERROR al crear el cliente (Código: {response.status_code}).")
            print("  Respuesta del API de Siigo:")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            return False

    except requests.exceptions.Timeout:
        print("ERROR: Tiempo de espera agotado al conectar con la API de Siigo.")
        return False
    except requests.exceptions.ConnectionError:
        print("ERROR: No se pudo establecer conexión con la API de Siigo.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"ERROR de conexión: {e}")
        return False
    except Exception as e:
        print(f"ERROR inesperado al crear cliente: {e}")
        return False

API_SIIGO_INVOICES_URL = "https://api.siigo.com/v1/invoices"

def create_invoice_siigo(access_token: str, invoice_data: dict):
    """
    Crea una factura en Siigo.
    Retorna:
      - (True, info_factura_dict) si todo ok
      - (False, mensaje_error) si falla
    """
    if not access_token or access_token == "TU_ACCESS_TOKEN":
        error_msg = "Token de acceso inválido o no proporcionado"
        print(f"¡ERROR! {error_msg}")
        return False, error_msg
    
    NOMBRE_DE_MI_APP = "AutomatizacionFacturasEncargomio"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Partner-Id": NOMBRE_DE_MI_APP
    }

    try:
        response = requests.post(API_SIIGO_INVOICES_URL, data=json.dumps(invoice_data), headers=headers)
        
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            error_msg = f"La respuesta no es un JSON válido. Código HTTP: {response.status_code}"
            print(f"ERROR: {error_msg}")
            print(f"Contenido de la respuesta: {response.text[:200]}")
            return False, error_msg

        if response.status_code == 201:
            inv_id   = response_data.get('id')
            name     = response_data.get('document', {}).get('name')
            prefix   = response_data.get('document', {}).get('prefix')
            consec   = response_data.get('consecutive')

            print("¡ÉXITO! Factura creada correctamente.")
            print(f"  ID de la factura creada: {inv_id}")
            print(f"  Número: {name}-{prefix}-{consec}")

            info_factura = {
                "id": inv_id,
                "name": name,
                "prefix": prefix,
                "consecutive": consec,
            }
            return True, info_factura
        else:
            error_detail = response_data.get('Errors', response_data.get('errors', response_data))
            error_msg = f"Error HTTP {response.status_code} - {error_detail}"
            print(f"ERROR al crear la factura (Código: {response.status_code}).")
            print("  Respuesta del API de Siigo:")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            return False, error_msg

    except requests.exceptions.Timeout:
        error_msg = "Tiempo de espera agotado al conectar con la API de Siigo"
        print(f"ERROR: {error_msg}.")
        return False, error_msg
    except requests.exceptions.ConnectionError:
        error_msg = "No se pudo establecer conexión con la API de Siigo"
        print(f"ERROR: {error_msg}.")
        return False, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Error de conexión: {str(e)}"
        print(f"ERROR: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Error inesperado: {str(e)}"
        print(f"ERROR: {error_msg}")
        return False, error_msg


def log_invoice_error(invoice_number, error_reason: str) -> bool:
    """
    Registra errores de facturas en un archivo de texto.
    """
    log_file = "errores_facturas.txt"
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{'='*80}\n")
            f.write(f"Fecha y Hora: {timestamp}\n")
            f.write(f"Número de Factura / ID_INGRESO: {invoice_number}\n")
            f.write(f"Razón del Error: {error_reason}\n")
            f.write(f"{'='*80}\n\n")
        
        print(f"\n⚠️  Error registrado en '{log_file}'")
        return True
    except Exception as e:
        print(f"\n⚠️  No se pudo guardar el error en el log: {e}")
        return False



run_facturacion_masiva

import requests
import json

SIIGO_BASE_URL = "https://api.siigo.com"

NOMBRE_DE_MI_APP = "AutomatizacionFacturasEncargomio"


def get_next_invoice_number(access_token: str) -> int | None:
    if not access_token:
        print("ERROR: access_token vacío al pedir el consecutivo de factura.")
        return None

    url = f"{SIIGO_BASE_URL}/v1/invoices"
    params = {
        "page_size": 1,
        "sort": "-date"
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Partner-Id": NOMBRE_DE_MI_APP
    }

    resp = requests.get(url, headers=headers, params=params, timeout=30)

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print("Respuesta no es JSON")
        print(resp.text[:500])
        return None

    print("==== RESPUESTA COMPLETA get_next_invoice_number ====")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    if resp.status_code != 200:
        print(f"ERROR HTTP {resp.status_code}")
        return None

    items = (
        data.get("results")
        or data.get("data")
        or data.get("items")
        or []
    )

    if not items:
        print("No se encontraron facturas. Usando consecutivo 1.")
        return 1

    last_inv = items[0]
    print("==== ÚLTIMA FACTURA SEGÚN API ====")
    print(json.dumps(last_inv, indent=2, ensure_ascii=False))

    consecutive = last_inv.get("consecutive") or last_inv.get("number")
    if consecutive is None:
        print("La última factura no trae número de consecutivo.")
        return None

    return int(str(consecutive))



def get_max_invoice_number(
    access_token: str,
    max_pages: int = 30,
    patience_pages: int = 3
) -> int | None:
    """
    Recorre varias páginas de /v1/invoices y calcula el número de factura máximo.
    Optimizado:
      - Se detiene si en 'patience_pages' páginas consecutivas
        ya no aparece un número mayor.
    """
    if not access_token:
        print("ERROR: access_token vacío al pedir el máximo consecutivo.")
        return None

    url = f"{SIIGO_BASE_URL}/v1/invoices"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Partner-Id": NOMBRE_DE_MI_APP
    }

    page = 1
    max_num = None
    sin_mejora = 0  # cuántas páginas seguidas vamos sin subir el máximo

    while page <= max_pages:
        params = {
            "page_size": 100,   # lo máximo que soporte Siigo
            "page": page
        }

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            try:
                data = resp.json()
            except json.JSONDecodeError:
                print(f"[page {page}] Respuesta no es JSON")
                print(resp.text[:500])
                break

            if resp.status_code != 200:
                print(f"[page {page}] ERROR HTTP {resp.status_code}")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                break

            items = (
                data.get("results")
                or data.get("data")
                or data.get("items")
                or []
            )

            if not items:
                print(f"[page {page}] Sin más facturas, fin del recorrido.")
                break

            mejoro_esta_pagina = False

            for inv in items:
                num = inv.get("consecutive") or inv.get("number")
                if num is None:
                    continue
                try:
                    n = int(str(num))
                except ValueError:
                    continue

                if (max_num is None) or (n > max_num):
                    max_num = n
                    mejoro_esta_pagina = True

            print(f"[page {page}] Procesadas {len(items)} facturas. Máximo hasta ahora: {max_num}")

            if mejoro_esta_pagina:
                sin_mejora = 0
            else:
                sin_mejora += 1
                if sin_mejora >= patience_pages:
                    print(f"🟡 No hay mejora en las últimas {patience_pages} páginas, se corta el recorrido.")
                    break

            page += 1

        except requests.exceptions.RequestException as e:
            print(f"ERROR de conexión en get_max_invoice_number (page {page}): {e}")
            break

    if max_num is None:
        print("No se pudo determinar un consecutivo máximo.")
    else:
        print(f"✅ Consecutivo máximo encontrado: {max_num}")

    return max_num




# ======================= BUILDERS DESDE EXCEL =======================

def build_customer_from_row(cli_row: pd.Series) -> dict:
    """
    Construye el customer_data para Siigo a partir de una fila de df_clientes.
    Usa la estructura básica que ya probaste.
    """
    identificacion = str(cli_row["Identificación (Obligatorio)"]).strip()
    nombres = str(cli_row["Nombres del tercero (Obligatorio)"]).strip()
    apellidos = str(cli_row["Apellidos del tercero (Obligatorio)"]).strip()
    direccion = str(cli_row.get("Dirección", "")).strip()
    cod_dep = str(cli_row.get("Código departamento/estado", "")).strip()
    cod_ciu = str(cli_row.get("Código ciudad", "")).strip()
    telefono = str(cli_row.get("Teléfono principal", "")).strip()
    email = str(cli_row.get("Correo electrónico contacto principal", "")).strip()

    customer_data = {
        "person_type": "Person",
        "id_type": "13",
        "identification": identificacion,
        "name": [nombres, apellidos],
        "address": {
            "address": direccion,
            "city": {
                "country_code": "Col",
                "state_code": cod_dep or "05",
                "city_code": cod_ciu or "05001"
            }
        },
        "phones": [
            {
                "number": telefono
            }
        ],
        "contacts": [
            {
                "first_name": nombres,
                "last_name": apellidos,
                "email": email
            }
        ]
    }
    return customer_data


from datetime import datetime

IVA_19_ID = 8368




OBSERVACIONES_POR_CASILLERO = {
    "9680": (
        "Esta factura corresponde a compras realizadas, por medio de J&L Suministros. Los cuales ya se encuentran pagos."
    ),
    "13608": (
        "Esta factura corresponde a pedidos realizados, por medio de NEWTEC SAS / DATEC SAS. Los cuales ya se encuentran pagos."
    ),
    "1633": (
        "Esta factura corresponde a pedidos realizados, por medio de INJ personal shopper. Los cuales ya se encuentran pagos."
    ),
    "1444": (
        "Esta factura corresponde a compras o envíos realizados, por medio de @mariapazshop Tienda de Instagram. Los cuales ya se encuentran pagos"
    ),
}






def build_invoice_from_row(
    ing_row: pd.Series,
    doc_id: int,
    seller_id: int,
    payment_id: int,
    iva_19_id: int,
    number: int,
    casillero_actual: str
) -> dict:
 #   """
  #  Construye el payload de factura para Agiom a partir de una fila de ingreso.

   # Lógica financiera (T = total cobrado al cliente en COP):
    #    GN1   = T / 1.015                → ingreso para terceros (sin IVA)
     #   SR02  = (GN1 * 0.015) / 1.19     → comisión base (sin IVA)
      #  IVA   = SR02 * 0.19              → IVA de la comisión
       # GN1 + SR02 + IVA ≈ T
    #"""

    # 1) Fecha de la factura
    fecha = datetime.now().strftime("%Y-%m-%d")

    # 2) Identificación del cliente (ya validada antes)
    customer_ident = str(ing_row.get("Id_cliente", "")).strip()

    # 3) Total cobrado al cliente (T)
    total = None
    for col in ["Monto COP", "MontoCOP", "Monto"]:
        if col in ing_row.index and pd.notna(ing_row[col]):
            try:
                total = float(ing_row[col])
                break
            except Exception:
                continue

    if total is None or not math.isfinite(total):
        total = 0.0

    T = total

    # 4) Cálculo GN1, SR02 (base) e IVA
    if T <= 0:
        GN1 = 0.0
        SR02_base = 0.0
        IVA_val = 0.0
    else:
        GN1 = T / 1.015
        SR02_base = (GN1 * 0.015) / 1.19

        # IVA según el ID que recibimos (si por alguna razón viene None, no calculamos IVA)
        if iva_19_id is not None:
            IVA_val = SR02_base * 0.19
        else:
            IVA_val = 0.0

        # Redondeo a 2 decimales
        GN1 = round(GN1, 2)
        SR02_base = round(SR02_base, 2)
        IVA_val = round(IVA_val, 2)

    # 🔹 4.1) Total de la factura según los ítems (lo que Siigo también va a ver)
    invoice_total = round(GN1 + SR02_base + IVA_val, 2)

    # 5) ID del IVA en Siigo (ya viene por parámetro)
    IVA_ID = IVA_19_ID   # aquí sí usamos el parámetro

    # Tercero del ingreso para terceros
    TERCERO_INGRESO_IDENT = "831412937"  # NIT de Largo Easy Corp

    # 6) Observaciones con referencia al ID_INGRESO (solo como texto)
    obs = OBSERVACIONES_POR_CASILLERO[str(casillero_actual)]

    # 7) Construcción del payload para Siigo
    invoice_data = {
        "document": {
            "id": doc_id
        },
        "date": fecha,
        "number": int(number),  # consecutivo que ya calculaste (última + 1)
        "customer": {
            "identification": customer_ident
        },
        "stamp": {
            "send": False
        },
        "mail": {
            "send": False
        },
        "seller": seller_id,
        "items": [
            {
                # 1️⃣ Ingreso para terceros (sin IVA)
                "code": "GN1",
                "quantity": 1,
                "price": GN1,
                "taxes": [],
                "customer": {
                    "identification": TERCERO_INGRESO_IDENT
                }
            },
            {
                # 2️⃣ Comisión Encargomio Colombia (con IVA)
                "code": "SR02",
                "quantity": 1,
                "price": SR02_base,      # base sin IVA
                "taxes": (
                    [{"id": IVA_ID}] if IVA_ID is not None else []
                )
            }
        ],
        "payments": [
            {
                "id": payment_id,
                # 🔹 El pago debe ser exactamente igual al total de la factura
                "value": invoice_total,
                "due_date": fecha
            }
        ],
        "observations": obs,
        "additional_fields": {}
    }

    return invoice_data




# ======================= FACTURACIÓN MASIVA DESDE EXCEL =======================

def run_facturacion_masiva(
    df_ing_pend: pd.DataFrame,
    df_clientes: pd.DataFrame,
    doc_id: int,
    seller_id: int,
    payment_id: int,
    casillero_actual: str,              # 👈 NUEVO (OBLIGATORIO)
    iva_19_id: int | None = None,
    source_filename: str | None = None,
):
    #"""
   # Reemplaza al main() del repo:
    #- Usa df_ing_pend (ingresos con Id_cliente y Factura vacía, ya preparados)
    #- Usa df_clientes (todos los clientes del casillero)
    #Además:
    #- Crea cliente en Siigo si no existe.
    #- Crea factura en Siigo.
    #- Escribe el número de factura en df_ing_pend["Factura"].
    #- Actualiza el Excel original de ingresos en Dropbox usando ID_INGRESO.
    #"""
    st.write("=== Iniciando proceso de facturación MASIVA en Siigo ===")

    # 1) Obtener token una sola vez
    st.write("1️⃣ Obteniendo token de autenticación...")
    token = obtain_token()
    if not token:
        st.error("ERROR CRÍTICO: No se pudo obtener el token de autenticación. No se puede continuar.")
        return

    # 2) Consultar desde Siigo el ÚLTIMO número de factura
    st.write("2️⃣ Calculando máximo número de factura en Siigo (recorriendo varias páginas)...")
    last_number = get_max_invoice_number(token, max_pages=30)  # por ejemplo 30 páginas
    
    if last_number is None:
        st.error(
            "No se pudo calcular el consecutivo máximo de facturas en Siigo. "
            "Revisa logs de get_max_invoice_number."
        )
        return
    
    current_number = int(last_number) + 1
    # 🔒 Límite legal de numeración de facturas
    FACTURA_MAX_NUMERO = 150_000
    
    if current_number > FACTURA_MAX_NUMERO - 1:
        st.error(
            f"❌ No es posible continuar con la facturación.\n\n"
            f"El consecutivo de facturación alcanzó el límite legal permitido "
            f"({FACTURA_MAX_NUMERO - 1}).\n\n"
            f"Último consecutivo detectado: {last_number}."
        )
        return

    st.write(f"➡️ Primer número de factura a usar (max + 1): {current_number}")


    # Índice por identificación para acceso rápido
    cli_idx = {
        str(row["Identificación (Obligatorio)"]).strip(): row
        for _, row in df_clientes.iterrows()
    }

    total = len(df_ing_pend)
    ok_count = 0
    err_count = 0

    # Asegurar que exista columna Factura en el DF de pendientes
    if "Factura" not in df_ing_pend.columns:
        df_ing_pend["Factura"] = pd.NA

    for i, (idx, ing_row) in enumerate(df_ing_pend.iterrows(), start=1):
        ident = str(ing_row.get("Id_cliente", "")).strip()
        id_ingreso = ing_row.get("ID_INGRESO", f"fila_{i}")

        st.write(
            f"--- ({i}/{total}) Procesando ingreso {id_ingreso} | "
            f"cliente {ident} | factura sugerida inicial {current_number} ---"
        )

        if not ident:
            msg = "Id_cliente vacío en el ingreso."
            st.warning(msg)
            log_invoice_error(id_ingreso, msg)
            err_count += 1
            continue

        cli_row = cli_idx.get(ident)
        if cli_row is None:
            msg = f"Cliente {ident} no está en la base de Clientes del casillero."
            st.warning(msg)
            log_invoice_error(id_ingreso, msg)
            err_count += 1
            continue

        # 3) Verificar/crear cliente en Siigo
        exists = verify_customer(token, ident)
        if not exists:
            st.write(f"Cliente {ident} no existe en Siigo. Creando...")
            customer_data = build_customer_from_row(cli_row)
            if not create_customer_siigo(token, customer_data):
                msg = f"No se pudo crear el cliente {ident} en Siigo."
                st.error(msg)
                log_invoice_error(id_ingreso, msg)
                err_count += 1
                continue

        # 4) Intentar crear la factura con mecanismo de reintento
        intentos = 0
        max_intentos = 20  # por si acaso, para no quedar en bucle infinito

        while intentos < max_intentos:
            intentos += 1
            numero_en_uso = current_number
            # 🔒 Corte duro por límite legal de facturación
            if numero_en_uso > FACTURA_MAX_NUMERO - 1:
                msg = f"Se alcanzó el límite legal de facturación ({FACTURA_MAX_NUMERO - 1})."
                st.error("❌ " + msg)
                return


            st.write(f"   ➜ Intento #{intentos} con número de factura {numero_en_uso} ...")

            try:
                invoice_data = build_invoice_from_row(
                    ing_row=ing_row,
                    doc_id=doc_id,
                    seller_id=seller_id,
                    payment_id=payment_id,
                    iva_19_id=iva_19_id,
                    number=numero_en_uso,
                    casillero_actual=str(casillero_actual),
                )

            except Exception as e:
                err_msg = f"Error armando la factura para ingreso {id_ingreso}: {e}"
                st.error(err_msg)
                log_invoice_error(id_ingreso, err_msg)
                err_count += 1
                break  # salimos del while para pasar al siguiente ingreso

            ok, err_msg = create_invoice_siigo(token, invoice_data)

            if ok:
                # ÉXITO: guardamos el número y avanzamos al siguiente ingreso
                num_factura = str(numero_en_uso)
                df_ing_pend.loc[idx, "Factura"] = num_factura
                st.success(
                    f"✅ Factura {num_factura} creada correctamente para ingreso {id_ingreso}"
                )
                ok_count += 1
                current_number = numero_en_uso + 1  # siguiente número base para la próxima factura
                break  # salimos del while intentos

            # Si NO ok:
            texto_err = str(err_msg or "")
            if "already_exists" in texto_err or "number already exists" in texto_err:
                st.warning(
                    f"⚠️ El número {numero_en_uso} ya existe en Siigo. "
                    "Probando con el siguiente consecutivo..."
                )
                current_number = numero_en_uso + 1
                continue  # reintenta con el nuevo current_number

            # Otro tipo de error → no tiene sentido seguir probando con +1
            err_count += 1
            log_invoice_error(id_ingreso, err_msg or "Error desconocido")
            st.error(f"❌ Error creando factura para ingreso {id_ingreso}: {err_msg}")
            break  # salimos del while para pasar al siguiente ingreso

        else:
            # Si se acabaron los intentos (while terminó por condición, no por break)
            msg = (
                f"No se pudo crear factura para ingreso {id_ingreso} "
                f"después de {max_intentos} intentos de consecutivo."
            )
            st.error("❌ " + msg)
            log_invoice_error(id_ingreso, msg)
            err_count += 1

    st.write("=== Proceso de facturación finalizado ===")
    st.write(f"✔️ Facturas creadas: {ok_count}")
    st.write(f"⚠️ Errores: {err_count}")

    # 5) Actualizar el Excel original en Dropbox USANDO EL ARCHIVO DEL BANCO
    try:
        df_to_update = df_ing_pend.dropna(subset=["Factura"])
        if df_to_update.empty:
            st.write("ℹ️ No hay facturas nuevas para actualizar en el Excel.")
            return

        if not source_filename:
            st.write("ℹ️ No se recibió 'source_filename', no se actualiza Excel en Dropbox.")
            return

        base_folder = get_base_folder()
        fullpath = f"{base_folder}/{source_filename}"

        df_file = _try_download_excel(fullpath)
        if df_file is None or df_file.empty:
            st.error(f"⚠️ No se pudo leer el archivo de ingresos en Dropbox: {fullpath}")
            return

        # Asegurar columnas clave
        if "ID_INGRESO" not in df_file.columns:
            df_file["ID_INGRESO"] = pd.NA
        if "Factura" not in df_file.columns:
            df_file["Factura"] = pd.NA

        for _, r in df_to_update.iterrows():
            id_ing = r.get("ID_INGRESO")
            factura = r.get("Factura")

            if pd.isna(id_ing):
                continue
            if pd.isna(factura) or str(factura).strip() == "":
                continue

            mask = (
                df_file["ID_INGRESO"]
                .astype(str).str.strip()
                .eq(str(id_ing).strip())
            )
            df_file.loc[mask, "Factura"] = factura

        # Guardar archivo actualizado en Dropbox
        buf_up = io.BytesIO()
        with pd.ExcelWriter(buf_up, engine="openpyxl") as w:
            df_file.to_excel(w, index=False, sheet_name="Ingresos")
        buf_up.seek(0)
        dbx.files_upload(
            buf_up.read(),
            fullpath,
            mode=dropbox.files.WriteMode.overwrite
        )

        st.write(f"🔄 Excel de ingresos actualizado con las facturas en: {source_filename}")

    except Exception as e:
        st.error(f"⚠️ No se pudo actualizar el Excel de ingresos con las facturas: {e}")









st.subheader("2️⃣ Ejecutar facturación automática en Siigo")

if st.button("🚀 Realizar facturación", use_container_width=True):
    df_pend = st.session_state.get("facturacion_ingresos_pendientes")
    df_clientes_fact = st.session_state.get("facturacion_clientes_actual")

    if df_pend is None or df_pend.empty:
        st.error("No hay ingresos pendientes preparados. Primero usa el botón 'Preparar facturación'.")
    elif df_clientes_fact is None or df_clientes_fact.empty:
        st.error("La base de clientes no está cargada. Revisa el paso de preparación.")
    else:
        DOC_ID = 15554   # id del documento de factura
        SELLER_ID = 401  # vendedor
        PAYMENT_ID = 8125  # forma de pago
        
        run_facturacion_masiva(
            df_ing_pend=df_pend,
            df_clientes=df_clientes_fact,
            doc_id=DOC_ID,
            seller_id=SELLER_ID,
            payment_id=PAYMENT_ID,
            casillero_actual=str(casillero_actual),   # 👈 NUEVO
            iva_19_id=IVA_19_ID,
            source_filename=fname_sel,
        )








build_invoice_from_row


#####################################################################################################################

# ——————————————————————————————
# 9) Todas las gráficas al final con numeración corregida
# ——————————————————————————————

# 9.1️⃣ Evolución del saldo reportado (#4)
st.header("4️⃣ Evolución del saldo reportado")
try:
    df_tot = df[df['Tipo']=='Total']
    if df_tot.empty:
        st.info("Aún no hay movimientos totales para mostrar.")
    else:
        df_tot = df_tot.copy()
        # asegurar tipos
        df_tot['Fecha de Carga'] = pd.to_datetime(df_tot['Fecha de Carga'], errors='coerce')
        df_tot['Monto'] = pd.to_numeric(df_tot['Monto'], errors='coerce')
    
        # tomar las 7 fechas de carga más recientes (distintas)
        fechas_recientes = (
            df_tot['Fecha de Carga']
            .dt.normalize()            # sólo la fecha (sin hora)
            .dropna()
            .drop_duplicates()
            .sort_values(ascending=False)
            .head(7)
        )
        # filtrar al conjunto de esas 7 fechas
        df_tot = df_tot[df_tot['Fecha de Carga'].dt.normalize().isin(set(fechas_recientes))]
        # ordenar por fecha para que la línea salga prolija
        df_tot = df_tot.sort_values('Fecha de Carga')
    
        fig, ax = plt.subplots(figsize=(8,4))
    
        # 1) línea gris de fondo
        ax.plot(df_tot['Fecha de Carga'], df_tot['Monto'],
                linestyle='-', color='lightgrey', linewidth=1)
    
        # 2) marcadores individuales coloreados
        for _, row in df_tot.iterrows():
            pt_color = 'green' if row['Monto'] >= 0 else 'red'
            ax.scatter(row['Fecha de Carga'], row['Monto'], color=pt_color, s=50, zorder=3)
    
        ax.set_title("Conciliación por día")
        ax.set_xlabel("Fecha de Carga")
        ax.set_ylabel("Saldo")
        ax.yaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
    
        # 3) anotaciones desplazadas
        for _, row in df_tot.iterrows():
            ann_color = 'green' if row['Monto'] >= 0 else 'red'
            label = f"{row['Fecha de Carga'].date()}\n${row['Monto']:,.0f}"
            offset = 30 if row['Monto'] >= 0 else -30
            ax.annotate(
                label,
                xy=(row['Fecha de Carga'], row['Monto']),
                xytext=(0, offset),
                textcoords="offset points",
                fontsize=8,
                ha='center',
                color=ann_color
            )
    
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.pyplot(fig)

except Exception as e:
    st.error(f"⚠️ Error sección Evolución del saldo: {e}")

# 9.2️⃣ Cantidad de compras (últimos 7 días) (#5)
st.header("5️⃣ Cantidad de compras (últimos 7 días)")
try:
    df_eg2 = df[df['Tipo']=='Egreso'].copy()
    if df_eg2.empty:
        st.info("Aún no hay compras para el cálculo de los últimos 7 días.")
    else:
        df_eg2['Fecha'] = pd.to_datetime(df_eg2['Fecha'])
        max_f = df_eg2['Fecha'].max()
        min_f = max_f - pd.Timedelta(days=6)
        conteo = df_eg2[(df_eg2['Fecha'] >= min_f) & (df_eg2['Fecha'] <= max_f)].groupby('Fecha').size()
        if conteo.empty:
            st.info("No hay compras en los últimos 7 días.")
        else:
            fig2, ax2 = plt.subplots(figsize=(8,4))
            ax2.plot(conteo.index, conteo.values, marker='o', color='green')
            ax2.set_title(f"Cantidad de compras: {min_f.date()} al {max_f.date()}")
            ax2.set_xlabel("Fecha")
            ax2.set_ylabel("Cantidad de compras")
            ax2.set_ylim(0, conteo.max() + 5)
            for fecha, val in conteo.items():
                ax2.text(fecha, val + 0.5, str(val), fontsize=8, ha='center', color='green')
            with st.columns([1,2,1])[1]:
                st.pyplot(fig2)
except Exception as e:
    st.error(f"⚠️ Error sección Cantidad de compras: {e}")

# 9.3️⃣ Valor total de compras (últimos 7 días) (#6)
st.header("6️⃣ Valor total de compras (últimos 7 días)")
try:
    if df_eg2.empty:
        st.info("Sin datos de egresos para valores totales.")
    else:
        suma = df_eg2[(df_eg2['Fecha'] >= min_f) & (df_eg2['Fecha'] <= max_f)].groupby('Fecha')['Monto'].sum()
        if suma.empty or pd.isna(suma.max()):
            st.info("No hay valor de compras en los últimos 7 días.")
        else:
            fig3, ax3 = plt.subplots(figsize=(8,4))
            ax3.plot(suma.index, suma.values, marker='o', color='green')
            ax3.set_title(f"Valor de compras: {min_f.date()} al {max_f.date()}")
            ax3.set_xlabel("Fecha")
            ax3.set_ylabel("Monto acumulado")
            ax3.yaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
            ax3.set_ylim(0, suma.max() * 1.25)
            rango_s = suma.max() - suma.min() if suma.max() != suma.min() else suma.max()
            for fecha, val in suma.items():
                desplaz = max(rango_s * 0.1, suma.max() * 0.05)
                ax3.text(fecha, val + desplaz, f"${val:,.0f}", fontsize=8, ha='center', color='green')
            with st.columns([1,2,1])[1]:
                st.pyplot(fig3)
except Exception as e:
    st.error(f"⚠️ Error sección Valor total de compras: {e}")

# 9.4️⃣ Ingresos últimos 7 días (#7)
st.header("7️⃣ Ingresos últimos 7 días")
try:
    df_in2 = df[df['Tipo']=='Ingreso'].copy()
    if df_in2.empty:
        st.info("Aún no tenemos movimientos de ingresos.")
    else:
        df_in2['Fecha'] = pd.to_datetime(df_in2['Fecha'])
        max_i = df_in2['Fecha'].max()
        min_i = max_i - pd.Timedelta(days=6)
        suma_i = df_in2[(df_in2['Fecha'] >= min_i) & (df_in2['Fecha'] <= max_i)].groupby('Fecha')['Monto'].sum()
        if suma_i.empty or pd.isna(suma_i.max()):
            st.info("Aún no tenemos ingresos en los últimos 7 días.")
        else:
            fig4, ax4 = plt.subplots(figsize=(8,4))
            ax4.plot(suma_i.index, suma_i.values, marker='o', color='green')
            ax4.set_title(f"Ingresos: {min_i.date()} al {max_i.date()}")
            ax4.set_xlabel("Fecha")
            ax4.set_ylabel("Monto acumulado")
            ax4.yaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
            ax4.set_ylim(0, suma_i.max() * 1.2)
            rng_i = suma_i.max() - suma_i.min() if suma_i.max() != suma_i.min() else suma_i.max()
            for fecha, val in suma_i.items():
                d = max(rng_i * 0.1, suma_i.max() * 0.05)
                ax4.text(fecha, val + d, f"${val:,.0f}", fontsize=8, ha='center', color='green')
            with st.columns([1,2,1])[1]:
                st.pyplot(fig4)
except Exception as e:
    st.error(f"⚠️ Error sección Ingresos últimos 7 días: {e}")
