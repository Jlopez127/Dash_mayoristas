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
    df = df.drop(columns=['TRM'], errors='ignore')
    df['Fecha de Carga'] = pd.to_datetime(df['Fecha de Carga'])
    df['Fecha']         = pd.to_datetime(df['Fecha'], errors='coerce')
    df['Monto']         = pd.to_numeric(df['Monto'], errors='coerce')
    return df

# 3) Diccionario de claves por hoja
PASSWORDS = {
    "clave_nathalia":    "1633 - Nathalia Ospina",
    "clave_maira":       "9444 - Maira Alejandra Paez",
    "clave_jimmy":       "14856 - Jimmy Cortes",
    "clave_elvis":       "11591 - Paula Herrera",
    "clave_maria":       "1444 - Maria Moises",
    "clave_julian":       "13608 - julian sanchez"
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


st.header(f"📋 Conciliaciones: {sheet_name}")

# 6) Mostrar fecha de última actualización
ultima = df['Fecha de Carga'].max()
st.markdown(f"## Última actualización: **{ultima.strftime('%Y-%m-%d')}**")


st.header("💰 Saldo al cierre de la última actualización")

df_tot_ultima = df[(df["Tipo"]=="Total") & (df["Fecha de Carga"]==ultima)]
if not df_tot_ultima.empty:
    monto_tot = df_tot_ultima["Monto"].iloc[0]
    color = "green" if monto_tot >= 0 else "red"
    # creamos tres columnas y metemos el número en la del medio
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
st.markdown("<h3 style='text-align:center;'>2️⃣ Ingresos</h3>", unsafe_allow_html=True)
df_in = df.loc[df['Tipo'] == 'Ingreso', ['Fecha','Monto','Motivo','Nombre del producto']].copy()
if df_in.empty:
    st.info("Aún no hay ingresos para mostrar.")
else:
    # Motivo y ordenamiento por fecha (desc)
    df_in['Motivo'] = np.where(df_in['Motivo'] != 'Ingreso_extra',
                               'Consignacion cuenta propia',
                               df_in['Motivo'])
    df_in['Fecha'] = pd.to_datetime(df_in['Fecha'], errors='coerce')
    df_in = df_in.sort_values('Fecha', ascending=False, na_position='last')

    # Formatos de salida
    df_in['Fecha'] = df_in['Fecha'].dt.strftime('%Y-%m-%d')
    df_in['Monto'] = df_in['Monto'].map(lambda x: f"${x:,.0f}")
    st.dataframe(df_in, use_container_width=True)

# 8.2️⃣ Compras realizadas (Egresos) (tabla)
st.markdown("<h3 style='text-align:center;'>3️⃣ Compras realizadas (Egresos)</h3>", unsafe_allow_html=True)
df_eg = df.loc[df['Tipo'] == 'Egreso', ['Fecha','Orden','Monto','Nombre del producto']].copy()
if df_eg.empty:
    st.info("Aún no hay compras registradas.")
else:
    # Ordenamiento por fecha (desc)
    df_eg['Fecha'] = pd.to_datetime(df_eg['Fecha'], errors='coerce')
    df_eg = df_eg.sort_values('Fecha', ascending=False, na_position='last')

    # Formatos de salida
    df_eg['Fecha'] = df_eg['Fecha'].dt.strftime('%Y-%m-%d')
    df_eg['Monto'] = df_eg['Monto'].map(lambda x: f"${x:,.0f}")
    st.dataframe(df_eg, use_container_width=True)

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
