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

# 1) Configuración de la página
st.set_page_config(page_title="Dashboard Mayoristas", layout="wide")

# 2) Inicializa Dropbox
cfg_dbx = st.secrets["dropbox"]
dbx = dropbox.Dropbox(
    app_key=cfg_dbx["app_key"],
    app_secret=cfg_dbx["app_secret"],
    oauth2_refresh_token=cfg_dbx["refresh_token"],
)

@st.cache_data
def load_data(sheet_name: str) -> pd.DataFrame:
    """
    Descarga el Excel de Dropbox, carga sólo la hoja sheet_name
    y normaliza columnas.
    """
    _, res = dbx.files_download(cfg_dbx["remote_path"])
    df = pd.read_excel(io.BytesIO(res.content), sheet_name=sheet_name)
    df = df.drop(columns=['TRM', 'Motivo'], errors='ignore')
    df['Fecha de Carga'] = pd.to_datetime(df['Fecha de Carga'])
    df['Fecha']         = pd.to_datetime(df['Fecha'], errors='coerce')
    df['Monto']         = pd.to_numeric(df['Monto'], errors='coerce')
    return df

# 3) Diccionario de claves por hoja
PASSWORDS = {
    "clave_nathalia":    "1633 - Nathalia Ospina",
    "clave_maira":       "9444 - Maira Alejandra Paez",
    "clave_jimmy":       "14856 - Jimmy Cortes",
    "clave_elvis":       "11591 - Elvis",
    "clave_maria":       "1444 - Maria Moises",
}

# 4) Pedir clave en el sidebar
st.sidebar.title("🔒 Acceso Mayorista")
password = st.sidebar.text_input("Introduce tu clave", type="password")
if not password:
    st.sidebar.warning("Debes introducir tu clave para continuar")
    st.stop()
if password not in PASSWORDS:
    st.sidebar.error("Clave incorrecta")
    st.stop()

# 5) Carga de datos tras autenticación
sheet_name = PASSWORDS[password]
df = load_data(sheet_name)

# 6) Mostrar fecha de última actualización
ultima = df['Fecha de Carga'].max()
st.markdown(f"## Última actualización: **{ultima.strftime('%Y-%m-%d')}**")

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

st.header(f"📋 Conciliaciones: {sheet_name}")

# 1️⃣ Evolución del saldo reportado
st.header("1️⃣ Evolución del saldo reportado")
try:
    df_tot = df[df['Tipo']=='Total']
    if df_tot.empty:
        st.info("Aún no hay movimientos totales para mostrar.")
    else:
        fig, ax = plt.subplots(figsize=(8,4))
        ax.plot(df_tot['Fecha de Carga'], df_tot['Monto'], marker='o')
        ax.set_title("Conciliación por día")
        ax.set_xlabel("Fecha de Carga")
        ax.set_ylabel("Saldo")
        ax.yaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
        m_max, m_min = df_tot['Monto'].max(), df_tot['Monto'].min()
        rango = m_max - m_min if m_max != m_min else m_max
        for _, row in df_tot.iterrows():
            delta = max(rango * 0.03, m_max * 0.005)
            color = 'green' if row['Monto'] >= 0 else 'red'
            ax.text(
                row['Fecha de Carga'], row['Monto'] + delta,
                f"{row['Fecha de Carga'].date()}\n${row['Monto']:,.0f}",
                fontsize=8, ha='center', color=color
            )
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.pyplot(fig)
except Exception as e:
    st.error(f"⚠️ Error sección Evolución del saldo: {e}")

# 2️⃣ Compras realizadas (Egresos)
st.header("2️⃣ Compras realizadas (Egresos)")
try:
    df_eg = df[df['Tipo']=='Egreso'][['Fecha','Orden','Monto','Estado de Orden','Nombre del producto']]
    if df_eg.empty:
        st.info("Aún no hay compras registradas.")
    else:
        df_eg = df_eg.copy()
        df_eg['Monto'] = df_eg['Monto'].map(lambda x: f"${x:,.0f}")
        st.dataframe(df_eg, use_container_width=True)
except Exception as e:
    st.error(f"⚠️ Error sección Compras realizadas: {e}")

# 3️⃣ Cantidad de compras (últimos 7 días)
st.header("3️⃣ Cantidad de compras (últimos 7 días)")
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
            ax2.set_ylabel("Número de Egresos")
            ax2.set_ylim(0, conteo.max() + 5)
            for fecha, val in conteo.items():
                ax2.text(fecha, val + 0.5, str(val), fontsize=8, ha='center', color='green')
            with st.columns([1,2,1])[1]:
                st.pyplot(fig2)
except Exception as e:
    st.error(f"⚠️ Error sección Cantidad de compras: {e}")

# 4️⃣ Valor total de compras (últimos 7 días)
st.header("4️⃣ Valor total de compras (últimos 7 días)")
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
            ax3.set_ylabel("Monto de Egresos")
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

# 5️⃣ Ingresos
st.header("5️⃣ Ingresos")
try:
    df_in = df[df['Tipo']=='Ingreso'][['Fecha','Monto']]
    if df_in.empty:
        st.info("Aún no hay ingresos para mostrar.")
    else:
        df_in = df_in.copy()
        df_in['Monto'] = df_in['Monto'].map(lambda x: f"${x:,.0f}")
        st.dataframe(df_in, use_container_width=True)
except Exception as e:
    st.error(f"⚠️ Error sección Ingresos: {e}")

# 6️⃣ Ingresos últimos 7 días
st.header("6️⃣ Ingresos últimos 7 días")
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