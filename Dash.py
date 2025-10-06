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

# 🔄 Botón de refresco manual (opción A)
if st.sidebar.button("🔄 Refrescar datos"):
    # Limpia la caché de la función cacheada
    load_data.clear()
    # (Opcional) limpiar toda la caché de datos:
    # st.cache_data.clear()
    st.rerun()

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
