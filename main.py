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

CORE_METRICS = [
    "Revenue",
    "Growth (QoQ / MoM)",
    "Gross Margin",
    "EBITDA / Resultado operativo",
    "Cash disponible",
    "Runway",
    "Clientes / Unidades activas",
    "Concentración de ingresos",
    "Cash Flow operativo",
    "Headcount",
]

def portal_screen():
    auth = st.session_state["auth"]
    username = auth["username"]
    role = auth["role"]
    company = auth["company"]  # para cliente viene fijo

    # Sidebar: periodo
    with st.sidebar:
        st.write(f"**Usuario:** {username}")
        st.write(f"**Rol:** {role}")
        if st.button("Cerrar sesión"):
            st.session_state.pop("auth", None)
            st.rerun()

        st.header("Período")
        year = st.number_input("Año", min_value=2020, max_value=2100, value=datetime.now().year, step=1)
        quarter = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])
        month_in_q = st.selectbox("Mes dentro del quarter", [1, 2, 3])  # si lo querés mensual dentro del Q

        st.header("Empresa")
        st.info(f"Empresa asignada: {company}")

    st.subheader("Carga de Reporte")

    # -------- A) Upload RAW (obligatorio) --------
    st.markdown("### 1) Subir archivos (obligatorio)")
    uploaded_files = st.file_uploader(
        "Subí PDF / Excel / CSV (podés subir más de uno)",
        type=["pdf", "xlsx", "xls", "csv"],
        accept_multiple_files=True
    )

    # Guardamos estado en session para habilitar submit
    st.session_state["has_uploads"] = bool(uploaded_files)

    # -------- B) Carga manual core (obligatorio) --------
    st.markdown("### 2) Cargar métricas core (obligatorio)")
    st.caption("Completá las métricas core del período seleccionado.")

    manual = {}
    missing = []

    c1, c2 = st.columns(2)
    for i, m in enumerate(CORE_METRICS):
        col = c1 if i % 2 == 0 else c2
        with col:
            val = st.text_input(m, key=f"metric__{m}")  # text para permitir %, números, etc.
            manual[m] = val.strip()
            if manual[m] == "":
                missing.append(m)

    st.session_state["manual_ok"] = (len(missing) == 0)

    if missing:
        st.warning(f"Faltan {len(missing)} métricas: " + ", ".join(missing))

    # -------- C) Submit final (habilitado sólo si cumple ambos) --------
    st.markdown("### 3) Enviar reporte")
    ready = st.session_state["has_uploads"] and st.session_state["manual_ok"]

    st.button(
        "Submit final",
        disabled=not ready,
        help="Se habilita cuando subiste al menos 1 archivo y completaste todas las métricas core."
    )

    if ready and st.button("Confirmar envío"):
        # 1) Guardar RAW uploads local (MVP)
        saved_paths = []
        for f in uploaded_files:
            p = save_raw_upload(company, username, int(year), quarter, int(month_in_q), f)
            saved_paths.append(str(p))

        # 2) Guardar métricas manuales (JSON+CSV local)
        metrics_payload = {
            "manual_metrics": manual,
            "raw_files": saved_paths,
        }
        submission_path = save_submission(company, username, int(year), quarter, int(month_in_q), metrics_payload)

        st.success("Reporte enviado y guardado.")
        st.write("Submission:", submission_path)

        # 3) (FUTURO) Subir a Drive:
        # - crear carpeta si no existe: f"{company} {quarter} {year}"
        # - subir raw files
        # - generar excel resumen y subirlo


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

