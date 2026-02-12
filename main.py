
import re
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# =========================
# CONFIG
# =========================
APP_TITLE = "Cometa • Input Portal (Simple MVP)"
BASE_DIR = Path(__file__).parent
LOGO_PATH = BASE_DIR / "LogoCometa.png"
COMPANIES_FILE = BASE_DIR / "companies.csv"

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw_uploads"
SUB_DIR = DATA_DIR / "submissions"
RAW_DIR.mkdir(parents=True, exist_ok=True)
SUB_DIR.mkdir(parents=True, exist_ok=True)

# Core metrics (hardcode por ahora, luego lo leemos del Excel)
CORE_METRICS = [
    {"name": "Revenue", "what": "Ingresos del período"},
    {"name": "Gross Margin %", "what": "Margen bruto (%)"},
    {"name": "Burn Rate", "what": "Quema mensual (cash burn)"},
    {"name": "Runway (months)", "what": "Meses de runway"},
    {"name": "Active Customers", "what": "Clientes activos"},
]

# =========================
# HELPERS
# =========================
def safe_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", (text or "").strip())

def render_header():
    col1, col2 = st.columns([6, 1])
    with col1:
        st.title(APP_TITLE)
    with col2:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=120)

def load_companies() -> pd.DataFrame:
    if not COMPANIES_FILE.exists():
        # crea un archivo base si no existe
        df = pd.DataFrame([{"company": "Admin", "password": "adminpass"}])
        df.to_csv(COMPANIES_FILE, index=False)
    return pd.read_csv(COMPANIES_FILE).fillna("")

def check_login(company: str, password: str) -> bool:
    df = load_companies()
    row = df[df["company"] == company].head(1)
    if row.empty:
        return False
    return row.iloc[0]["password"] == password

def period_folder(company: str, year: int, quarter: str, month_in_q: int) -> Path:
    return Path(safe_name(company)) / str(year) / quarter / f"month_{month_in_q}"

def save_raw_upload(company: str, year: int, quarter: str, month_in_q: int, file) -> Path:
    dest_dir = RAW_DIR / period_folder(company, year, quarter, month_in_q)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = re.sub(r"[^a-zA-Z0-9._-]+", "_", file.name)
    dest_path = dest_dir / f"{ts}__{filename}"
    with open(dest_path, "wb") as f:
        f.write(file.getbuffer())
    return dest_path

def save_core_metrics(company: str, year: int, quarter: str, month_in_q: int, metrics: dict) -> Path:
    dest_dir = SUB_DIR / period_folder(company, year, quarter, month_in_q)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    payload = {
        "meta": {
            "company": company,
            "year": year,
            "quarter": quarter,
            "month_in_q": month_in_q,
            "submitted_at_utc": ts,
            "schema_version": "simple-mvp-1",
        },
        "metrics": metrics,
    }

    json_path = dest_dir / f"core_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # también guardamos CSV
    csv_path = dest_dir / f"core_{ts}.csv"
    pd.DataFrame([{"metric": k, "value": v} for k, v in metrics.items()]).to_csv(csv_path, index=False)

    return json_path

# =========================
# UI
# =========================
def login_screen():
    render_header()
    st.subheader("Login por compañía")

    df = load_companies()
    companies = df["company"].tolist()

    company = st.selectbox("Compañía", companies)
    password = st.text_input("Password", type="password")

    if st.button("Ingresar"):
        if check_login(company, password):
            st.session_state["company"] = company
            st.rerun()
        else:
            st.error("Credenciales incorrectas.")

def portal_screen():
    render_header()
    company = st.session_state["company"]

    with st.sidebar:
        st.write(f"**Compañía:** {company}")
        if st.button("Cerrar sesión"):
            st.session_state.pop("company", None)
            st.rerun()

        st.header("Período")
        year = st.number_input("Año", min_value=2020, max_value=2100, value=datetime.now().year, step=1)
        quarter = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])
        month_in_q = st.selectbox("Mes dentro del quarter", [1, 2, 3])

    tabs = st.tabs(["Upload reportes (raw)", "Carga manual (Core)"])

    # Upload raw
    with tabs[0]:
        st.subheader("Subir reportes en formato convencional")
        up = st.file_uploader("Subir archivo (xlsx/csv/pdf/etc.)", type=None)
        if up is not None and st.button("Guardar archivo"):
            path = save_raw_upload(company, int(year), quarter, int(month_in_q), up)
            st.success(f"Guardado: {path}")

    # Core manual
    with tabs[1]:
        st.subheader("Carga manual de métricas Core")
        st.caption("Estas métricas son las core acordadas para el MVP.")

        values = {}
        missing = []

        with st.form("core_form"):
            for m in CORE_METRICS:
                v = st.number_input(m["name"], value=0.0, step=0.01, help=m["what"])
                provided = st.checkbox(f"Incluir {m['name']}", value=True)
                if provided:
                    values[m["name"]] = float(v)
                else:
                    missing.append(m["name"])

            submitted = st.form_submit_button("Enviar métricas Core")

        if submitted:
            # Si querés core obligatorias, invertimos esto:
            # if missing: error
            # Por ahora permitimos enviar lo que haya.
            path = save_core_metrics(company, int(year), quarter, int(month_in_q), values)
            st.success(f"Métricas guardadas: {path}")

# =========================
# MAIN
# =========================
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    if "company" not in st.session_state:
        login_screen()
    else:
        portal_screen()

if __name__ == "__main__":
    main()
