import os
import io
import re
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import bcrypt

# -----------------------------
# Config
# -----------------------------
APP_TITLE = "Cometa • Input Portal (MVP)"
BASE_DIR = Path(__file__).parent
METRICS_FILE = BASE_DIR / "Metricas.xlsx"
USERS_FILE = BASE_DIR / "users.csv"
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw_uploads"
SUB_DIR = DATA_DIR / "submissions"

RAW_DIR.mkdir(parents=True, exist_ok=True)
SUB_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Helpers: Users & Auth
# -----------------------------
def _hash_password(plain: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")

def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def load_users() -> pd.DataFrame:
    if not USERS_FILE.exists():
        df = pd.DataFrame(columns=["company", "username", "password_hash", "role"])
        df.to_csv(USERS_FILE, index=False)

    df = pd.read_csv(USERS_FILE)
    # Normaliza
    for col in ["company", "username", "password_hash", "role"]:
        if col not in df.columns:
            df[col] = ""
    df["company"] = df["company"].fillna("").astype(str)
    df["username"] = df["username"].fillna("").astype(str)
    df["password_hash"] = df["password_hash"].fillna("").astype(str)
    df["role"] = df["role"].fillna("").astype(str)
    return df

def save_users(df: pd.DataFrame) -> None:
    df.to_csv(USERS_FILE, index=False)

def bootstrap_admin():
    """
    Si existe fila admin sin password_hash, pedimos setearla.
    """
    df = load_users()
    admin_rows = df[(df["username"] == "admin") & (df["role"] == "admin")]
    if admin_rows.empty:
        df = pd.concat([df, pd.DataFrame([{
            "company": "ALL",
            "username": "admin",
            "password_hash": "",
            "role": "admin"
        }])], ignore_index=True)
        save_users(df)
        return

# -----------------------------
# Helpers: Metrics
# -----------------------------
@st.cache_data(show_spinner=False)
def load_core_metrics():
    if not METRICS_FILE.exists():
        raise FileNotFoundError(f"No encuentro {METRICS_FILE}. Poné Metricas.xlsx junto a main.py")

    core = pd.read_excel(METRICS_FILE, sheet_name="Core")
    # Esperamos columnas: Métrica, Qué mide (pero toleramos nombres parecidos)
    core_cols = {c.lower().strip(): c for c in core.columns}

    metric_col = core_cols.get("métrica") or core_cols.get("metrica") or list(core.columns)[0]
    what_col = core_cols.get("qué mide") or core_cols.get("que mide")

    core = core[[metric_col] + ([what_col] if what_col else [])].copy()
    core.columns = ["metric", "what"] if what_col else ["metric"]

    core["metric"] = core["metric"].astype(str).str.strip()
    if "what" in core.columns:
        core["what"] = core["what"].astype(str).str.strip()
    else:
        core["what"] = ""

    core = core[core["metric"].ne("")].drop_duplicates(subset=["metric"]).reset_index(drop=True)
    return core

def metric_key(metric_name: str) -> str:
    # Crea una key estable para guardar
    k = metric_name.strip().lower()
    k = re.sub(r"[^a-z0-9]+", "_", k)
    k = re.sub(r"_+", "_", k).strip("_")
    return k

# -----------------------------
# Helpers: Storage
# -----------------------------
def company_dir(company: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", company.strip())
    return SUB_DIR / safe

def build_period_path(company: str, year: int, quarter: str, month_in_q: int) -> Path:
    # submissions/<company>/<year>/Q1/month_1/
    return company_dir(company) / str(year) / quarter / f"month_{month_in_q}"

def save_submission(company: str, user: str, year: int, quarter: str, month_in_q: int, payload: dict) -> Path:
    p = build_period_path(company, year, quarter, month_in_q)
    p.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "company": company,
        "user": user,
        "year": year,
        "quarter": quarter,
        "month_in_q": month_in_q,
        "submitted_at_utc": ts,
        "schema_version": "mvp-1"
    }

    # Guardamos JSON (fácil de evolucionar) y CSV (fácil para BI)
    json_path = p / f"submission_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "metrics": payload}, f, ensure_ascii=False, indent=2)

    csv_path = p / f"submission_{ts}.csv"
    rows = [{"metric": k, "value": v} for k, v in payload.items()]
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    return json_path

def save_raw_upload(company: str, user: str, year: int, quarter: str, month_in_q: int, uploaded_file) -> Path:
    # raw_uploads/<company>/<year>/Q1/month_1/<timestamp>_<filename>
    safe_company = re.sub(r"[^a-zA-Z0-9_-]+", "_", company.strip())
    dest_dir = RAW_DIR / safe_company / str(year) / quarter / f"month_{month_in_q}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = re.sub(r"[^a-zA-Z0-9._-]+", "_", uploaded_file.name)
    dest_path = dest_dir / f"{ts}__{filename}"

    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return dest_path

# -----------------------------
# UI: Auth screens
# -----------------------------
def login_screen():
    st.title(APP_TITLE)
    st.subheader("Login")

    bootstrap_admin()
    df_users = load_users()

    # Si admin no tiene password, forzamos seteo
    admin_row = df_users[(df_users["username"] == "admin") & (df_users["role"] == "admin")].head(1)
    if not admin_row.empty and (admin_row.iloc[0]["password_hash"] == "" or pd.isna(admin_row.iloc[0]["password_hash"])):
        st.warning("Primera vez: configurá la contraseña del admin.")
        new_pass = st.text_input("Nueva contraseña admin", type="password")
        new_pass2 = st.text_input("Repetir contraseña", type="password")
        if st.button("Guardar contraseña admin"):
            if not new_pass or len(new_pass) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
                st.stop()
            if new_pass != new_pass2:
                st.error("Las contraseñas no coinciden.")
                st.stop()

            idx = admin_row.index[0]
            df_users.loc[idx, "password_hash"] = _hash_password(new_pass)
            save_users(df_users)
            st.success("Contraseña admin configurada. Ahora logueate.")
            st.rerun()

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):
        if not username or not password:
            st.error("Completá usuario y contraseña.")
            return

        user_row = df_users[df_users["username"] == username].head(1)
        if user_row.empty:
            st.error("Usuario no encontrado.")
            return

        hashed = user_row.iloc[0]["password_hash"]
        if not hashed or not _verify_password(password, hashed):
            st.error("Contraseña incorrecta.")
            return

        st.session_state["auth"] = {
            "username": username,
            "role": user_row.iloc[0]["role"],
            "company": user_row.iloc[0]["company"],
        }
        st.success("Login OK")
        st.rerun()

def admin_user_mgmt():
    st.subheader("Admin • Usuarios")
    df = load_users()

    st.caption("Crear usuario de cliente (empresa + usuario + contraseña).")
    c1, c2, c3 = st.columns(3)
    with c1:
        company = st.text_input("Empresa (ej: Numia)")
    with c2:
        username = st.text_input("Usuario (ej: numia_admin)")
    with c3:
        role = st.selectbox("Rol", ["client"], index=0)

    pass1 = st.text_input("Contraseña", type="password")
    pass2 = st.text_input("Repetir contraseña", type="password")

    if st.button("Crear usuario"):
        if not company or not username:
            st.error("Empresa y usuario son obligatorios.")
            st.stop()
        if pass1 != pass2:
            st.error("Las contraseñas no coinciden.")
            st.stop()
        if len(pass1) < 8:
            st.error("La contraseña debe tener al menos 8 caracteres.")
            st.stop()
        if (df["username"] == username).any():
            st.error("Ese usuario ya existe.")
            st.stop()

        new_row = pd.DataFrame([{
            "company": company.strip(),
            "username": username.strip(),
            "password_hash": _hash_password(pass1),
            "role": role
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        save_users(df)
        st.success("Usuario creado.")

    st.divider()
    st.caption("Usuarios existentes:")
    st.dataframe(df[["company", "username", "role"]], use_container_width=True)

# -----------------------------
# UI: Main app (after login)
# -----------------------------
def app_screen():
    core = load_core_metrics()

    auth = st.session_state.get("auth", {})
    username = auth.get("username")
    role = auth.get("role")
    company_fixed = auth.get("company")

    st.title(APP_TITLE)
    st.caption(f"Logueado: {username} • rol: {role}")

    with st.sidebar:
        if st.button("Cerrar sesión"):
            st.session_state.pop("auth", None)
            st.rerun()

        st.header("Período")
        year = st.number_input("Año", min_value=2020, max_value=2100, value=datetime.now().year, step=1)
        quarter = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])
        month_in_q = st.selectbox("Mes dentro del quarter", [1, 2, 3])

        st.header("Empresa")
        # Admin puede elegir empresa libremente; cliente queda “fixed”
        if role == "admin":
            # Listado sugerido: desde users.csv (empresas únicas)
            dfu = load_users()
            companies = sorted([c for c in dfu["company"].unique().tolist() if c and c != "ALL"])
            company = st.selectbox("Seleccionar empresa", options=(companies if companies else ["(sin empresas en users.csv)"]))
        else:
            company = company_fixed
            st.info(f"Empresa asignada: {company}")

    tabs = st.tabs(["Carga guiada (Core)", "Upload (raw)", "Admin"])

    # -----------------------------
    # Tab 1: Form core
    # -----------------------------
    with tabs[0]:
        st.subheader("Carga guiada • Métricas Core")
        st.caption("Completá las métricas core. Las definiciones vienen del diccionario de métricas.")

        # Diccionario visible
        with st.expander("Ver diccionario de métricas (qué mide cada una)"):
            st.dataframe(core[["metric", "what"]], use_container_width=True)

        # Form
        values = {}
        missing = []

        with st.form("core_form", clear_on_submit=False):
            for _, row in core.iterrows():
                m = row["metric"]
                help_txt = row.get("what", "")
                key = f"m__{metric_key(m)}"

                # input numérico, permite vacío (None) con checkbox
                c1, c2 = st.columns([3, 1])
                with c1:
                    v = st.number_input(m, value=0.0, step=0.01, format="%.4f", help=help_txt, key=key)
                with c2:
                    provided = st.checkbox("Cargar", value=False, key=f"chk__{key}", help="Marcalo si querés enviar esta métrica")
                if provided:
                    values[m] = float(v)
                else:
                    # core: lo tratamos como requerido (en MVP)
                    missing.append(m)

            submitted = st.form_submit_button("Enviar métricas Core")

        if submitted:
            # Reporte de errores entendible
            if len(missing) > 0:
                st.error(
                    "No se pudo enviar: faltan métricas core obligatorias.\n\n"
                    + "\n".join([f"- {m}" for m in missing])
                )
                st.stop()

            # Persistencia
            path = save_submission(company, username, int(year), quarter, int(month_in_q), values)
            st.success(f"Submission guardada: {path}")

    # -----------------------------
    # Tab 2: Upload raw
    # -----------------------------
    with tabs[1]:
        st.subheader("Upload • Archivo raw")
        st.caption("Subí el archivo tal cual lo vienen entregando. Se guarda en raw_uploads por empresa y período.")

        up = st.file_uploader("Subir archivo (xlsx/csv/pdf/etc.)", type=None)
        if up is not None:
            if st.button("Guardar upload"):
                dest = save_raw_upload(company, username, int(year), quarter, int(month_in_q), up)
                st.success(f"Archivo guardado: {dest}")

    # -----------------------------
    # Tab 3: Admin
    # -----------------------------
    with tabs[2]:
        if role != "admin":
            st.info("Solo visible para admin.")
        else:
            admin_user_mgmt()

# -----------------------------
# Entrypoint
# -----------------------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    if "auth" not in st.session_state:
        login_screen()
    else:
        app_screen()

if __name__ == "__main__":
    main()
