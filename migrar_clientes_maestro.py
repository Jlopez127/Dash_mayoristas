"""
migrar_clientes_maestro.py

Migración one-off: consolida todos los Clientes_<casillero>.xlsx de Dropbox en un
único Clientes_MAESTRO.xlsx (3 columnas: Identificacion, Nombre, Tipo_ID).
NUNCA incluye PII (teléfono/correo/dirección). NO borra los archivos viejos.

Uso:
    python migrar_clientes_maestro.py            # DRY-RUN (no sube nada)
    python migrar_clientes_maestro.py --apply    # sube Clientes_MAESTRO.xlsx a Dropbox

Lee credenciales de .streamlit/secrets.toml [dropbox]. Si faltan -> aborta y avisa.
"""
import io
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(HERE, ".streamlit", "secrets.toml")

# archivos fuente: Clientes_<digitos>.xlsx (excluye backups _PRE_maestro y el propio MAESTRO)
PATRON_FUENTE = re.compile(r"^clientes_\d+\.xlsx$", re.IGNORECASE)
MAESTRO_NAME = "Clientes_MAESTRO.xlsx"

# columnas legacy posibles para identificación y nombre
IDENT_LEGACY = ["Identificacion", "Identificación (Obligatorio)"]
NOMBRE_LEGACY = ["Nombre", "Nombres del tercero (Obligatorio)"]
TIPO_ID_LEGACY = ["Tipo_ID", "Tipo identificación"]


def _clean_id(x) -> str:
    """Misma lógica que Dash._clean_id: str, strip, quita '.0', vacío para nan/none/..."""
    s = "" if x is None else str(x).strip()
    if s.lower() in {"", "nan", "none", "null", "<na>"}:
        return ""
    s = re.sub(r"\.0$", "", s)
    return s


def _first_col(df, candidatas):
    for c in candidatas:
        if c in df.columns:
            return c
    return None


def load_toml(path):
    data, sec = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sec = line[1:-1].strip(); data[sec] = {}
        elif "=" in line and sec is not None:
            k, v = line.split("=", 1); data[sec][k.strip()] = v.strip().strip('"').strip("'")
    return data


def main():
    apply = "--apply" in sys.argv

    if not os.path.exists(SECRETS):
        print(f"ERROR: no existe {SECRETS}. No hay credenciales Dropbox -> no se puede migrar.")
        sys.exit(2)
    cfg = load_toml(SECRETS).get("dropbox")
    if not cfg or "remote_path" not in cfg:
        print("ERROR: sección [dropbox] incompleta en secrets.toml.")
        sys.exit(2)

    import dropbox
    dbx = dropbox.Dropbox(app_key=cfg["app_key"], app_secret=cfg["app_secret"],
                          oauth2_refresh_token=cfg["refresh_token"])
    base = "/".join(cfg["remote_path"].rstrip("/").split("/")[:-1])
    print(f"Carpeta Dropbox: {base}")
    print(f"Modo: {'APLICAR (subirá el maestro)' if apply else 'DRY-RUN (no sube nada)'}\n")

    # listar
    res = dbx.files_list_folder(base); entries = list(res.entries)
    while res.has_more:
        res = dbx.files_list_folder_continue(res.cursor); entries.extend(res.entries)
    fuentes = sorted([e.name for e in entries
                      if hasattr(e, "size") and PATRON_FUENTE.match(e.name)])
    print(f"Archivos fuente detectados ({len(fuentes)}):")
    for f in fuentes:
        print(f"   {f}")
    if not fuentes:
        print("No hay archivos Clientes_<cas>.xlsx. Nada que migrar."); sys.exit(1)

    # concatenar
    frames = []
    resumen_origen = {}
    for name in fuentes:
        _, r = dbx.files_download(f"{base}/{name}")
        df = pd.read_excel(io.BytesIO(r.content))
        c_id = _first_col(df, IDENT_LEGACY)
        c_nom = _first_col(df, NOMBRE_LEGACY)
        c_tip = _first_col(df, TIPO_ID_LEGACY)
        if c_id is None or c_nom is None:
            print(f"   ⚠️ {name}: sin columna de ident/nombre reconocible (id={c_id}, nom={c_nom}); se omite.")
            resumen_origen[name] = 0
            continue
        sub = pd.DataFrame({
            "Identificacion": df[c_id].map(_clean_id),
            "Nombre": df[c_nom].astype(str).str.strip(),
            "Tipo_ID": (df[c_tip].astype(str).str.strip() if c_tip else "13"),
        })
        sub = sub[sub["Identificacion"] != ""]
        sub["Tipo_ID"] = sub["Tipo_ID"].replace({"": "13", "nan": "13", "None": "13"}).fillna("13")
        resumen_origen[name] = len(sub)
        frames.append(sub)

    todos = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["Identificacion", "Nombre", "Tipo_ID"])
    total_pre = len(todos)

    # dedup por Identificacion: conservar el NOMBRE MÁS LARGO
    todos["_len"] = todos["Nombre"].astype(str).str.len()
    todos = (todos.sort_values("_len", ascending=False)
                  .drop_duplicates(subset=["Identificacion"], keep="first")
                  .drop(columns="_len")
                  .sort_values("Identificacion")
                  .reset_index(drop=True))
    total_post = len(todos)
    dups = total_pre - total_post

    print("\n=== RESUMEN ===")
    for name, n in resumen_origen.items():
        print(f"   {name:40} -> {n:6,} filas")
    print(f"   {'TOTAL concatenado':40} -> {total_pre:6,} filas")
    print(f"   {'Duplicados eliminados':40} -> {dups:6,}")
    print(f"   {'MAESTRO final (docs únicos)':40} -> {total_post:6,} filas")
    print(f"   Columnas del maestro: {list(todos.columns)}")
    print("\n   Muestra (5):")
    for _, r in todos.head(5).iterrows():
        print(f"      {str(r['Identificacion']):>14} | {str(r['Nombre'])[:34]:34} | Tipo_ID={r['Tipo_ID']}")

    if not apply:
        print("\n*** DRY-RUN: no se subió nada. Ejecuta con --apply para crear Clientes_MAESTRO.xlsx. ***")
        return

    # subir maestro (NO borra nada viejo)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        todos.to_excel(w, index=False, sheet_name="Clientes")
    buf.seek(0)
    dbx.files_upload(buf.read(), f"{base}/{MAESTRO_NAME}", mode=dropbox.files.WriteMode.overwrite)
    md = dbx.files_get_metadata(f"{base}/{MAESTRO_NAME}")
    print(f"\n✅ SUBIDO: {MAESTRO_NAME} ({md.size:,} bytes). Archivos viejos NO se tocaron.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
