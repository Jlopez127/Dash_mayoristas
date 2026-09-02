# Dash_mayoristas — guía de trabajo

Visor del histórico de mayoristas (`Dash.py`, Streamlit). **Solo LEE** el histórico de Dropbox;
nunca lo escribe. Quien lo escribe es el repo hermano **`Mayoristas_app`** — si el problema es
un dato equivocado y no una tabla, el arreglo va allá.

---

## Reglas

1. **No romper nada que ya funcione.** Cambios quirúrgicos, no reescrituras.
2. **Trabajar en rama**, commit pequeño, merge `--no-ff`.
3. **Probar contra el histórico real** antes de mergear: bajar el vivo de Dropbox y replicar el
   bloque que se cambió.
4. Si un cambio se pide para **un casillero**, gatearlo por `sheet_name` — no dejarlo genérico.
   Ya pasó dos veces que una columna pedida para 1444 apareció en todos.

---

## Trampas conocidas

### ⚠️ `load_data` le suma +100 a la TRM de 1444

```python
df['TRM'] = pd.to_numeric(df['TRM'], errors='coerce').add(100)
```

Regla legacy de cuando los **ingresos** de 1444 venían en USD. **No es la TRM de nada más:**
las tarjetas se cobran con oficial **+125** y los envíos traen su propia TRM.

Por eso `load_data` guarda el valor crudo en **`TRM_envio`** antes del `+100` (y antes del
`drop` de la columna TRM en las hojas que no son de 1444). **Cualquier columna nueva que muestre
TRM debe usar `TRM_envio`, nunca `TRM`.**

> El consumidor original del `+100` era la columna `Monto COP`, retirada el 26-ago-2026 porque
> los ingresos ya vienen en COP y multiplicarlos por la TRM daba cifras absurdas (un ingreso de
> 3.980 millones se mostraba como 12,8 **billones**). Hoy el `+100` solo afecta lo que se ve en
> la columna TRM de la tabla de ingresos.

### ⚠️ La columna `TRM` del histórico no es solo de envíos

La llenan también las filas de tarjeta y las compras legacy. En 1444 son 471 legacy + 185
Robinhood + 149 Amex contra 23 envíos. **Enmascarar por `Motivo == 'Envio'`** antes de mostrarla
como TRM de un envío.

### ⚠️ `df_in` y `df_eg` alimentan tres cosas

La tabla en pantalla, el **Excel de descarga** y el **Consolidado**. Una columna añadida a
cualquiera de los dos aparece en los tres. Decidir a propósito en cuáles debe verse.

Decisiones vigentes en `df_eg`: `Peso (lb)`, `TRM` y **`Fecha de Carga`** se ven en pantalla y
en el Excel de egresos, pero se **retiran del Consolidado** (del lado de los ingresos quedarían
vacías). El retiro se hace en el `drop` de `df_eg_c`.

---

## Dónde está cada cosa

Buscar por nombre, no por línea:

- **Carga y normalización**: `load_data`
- **Tabla de ingresos**: buscar `2️⃣ Ingresos` → `df_in`
- **Tabla de egresos**: buscar `3️⃣ Compras realizadas` → `df_eg`
- **Consolidado**: buscar `🧾 Consolidado`
- **Filtro de fecha**: `start_date` (por `Fecha de Carga`, default = todo)
