import re
import json
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# =========================================================
# CONFIG
# =========================================================
APP_TITLE = "Cometa • Input Portal (MVP)"
BASE_DIR = Path(__file__).parent

LOGO_PATH = BASE_DIR / "LogoCometa.png"
USERS_FILE = BASE_DIR / "users.csv"

DATA_DIR = BASE_DIR / "data"
SUB_DIR = DATA_DIR / "submissions"
RAW_DIR = DATA_DIR / "raw_uploads"

SUB_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# UTILS
# =========================================================
def safe_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", (text or "").strip())


def render_header():
    col1, col2 = st.columns([6, 1])
    with col1:
        st.title(APP_TITLE)
    with col2:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=120)
        else:
            st.caption("LogoCometa.png no encontrado")


# =========================================================
# AUTH (users.csv + hashlib)
# =========================================================
def _hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _verify_password(plain: str, hashed: str) -> bool:
    return _hash_password(plain) == (hashed or "")


def load_users() -> pd.DataFrame:
    if not USERS_FILE.exists():
        df = pd.DataFrame(columns=["company", "username", "password_hash", "role"])
        df.to_csv(USERS_FILE, index=False)

    df = pd.read_csv(USERS_FILE).fillna("")
    for col in ["company", "username", "password_hash", "role"]:
        if col not in df.columns:
            df[col] = ""
    return df


def save_users(df: pd.DataFrame) -> None:
    df.to_csv(USERS_FILE, index=False)


def ensure_admin_exists():
    df = load_users()
    exists = ((df["username"] == "admin") & (df["role"] == "admin")).any()
    if not exists:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    [{"company": "ALL", "username": "admin", "password_hash": "", "role": "admin"}]
                ),
            ],
            ignore_index=True,
        )
        save_users(df)


def login_screen():
    ensure_admin_exists()
    df_users = load_users()

    st.subheader("Login")

    # 1st run: if admin has no password_hash, force setup
    admin_row = df_users[(df_users["username"] == "admin") & (df_users["role"] == "admin")].head(1)
    if not admin_row.empty and admin_row.iloc[0]["password_hash"] == "":
        st.warning("Primera vez: configurá la contraseña del admin.")
        p1 = st.text_input("Nueva contraseña admin", type="password")
        p2 = st.text_input("Repetir contraseña", type="password")
        if st.button("Guardar contraseña admin"):
            if not p1 or len(p1) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
                st.stop()
            if p1 != p2:
                st.error("Las contraseñas no coinciden.")
                st.stop()
            idx = admin_row.index[0]
            df_users.loc[idx, "password_hash"] = _hash_password(p1)
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

        if not _verify_password(password, user_row.iloc[0]["password_hash"]):
            st.error("Contraseña incorrecta.")
            return

        st.session_state["auth"] = {
            "username": username,
            "role": user_row.iloc[0]["role"],
            "company": user_row.iloc[0]["company"],
        }
        st.rerun()


# =========================================================
# STORAGE
# =========================================================
def save_submission(company: str, username: str, year: int, quarter: str, month_in_q: int, payload: dict) -> Path:
    safe_company = safe_name(company)
    p = SUB_DIR / safe_company / str(year) / quarter / f"month_{month_in_q}"
    p.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = {
        "meta": {
            "company": company,
            "username": username,
            "year": year,
            "quarter": quarter,
            "month_in_q": month_in_q,
            "submitted_at_utc": ts,
            "schema_version": "mvp-1",
        },
        "data": payload,
    }

    json_path = p / f"submission_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return json_path


# =========================================================
# ADMIN UI
# =========================================================
def admin_panel():
    st.subheader("Admin • Gestión de usuarios")
    df = load_users()

    with st.expander("Crear usuario cliente", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            company = st.text_input("Empresa (ej: Kala)")
            username = st.text_input("Usuario (ej: kala_admin)")
        with c2:
            p1 = st.text_input("Contraseña", type="password")
            p2 = st.text_input("Repetir contraseña", type="password")

        if st.button("Crear usuario"):
            if not company or not username:
                st.error("Empresa y usuario son obligatorios.")
                st.stop()
            if len(p1) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
                st.stop()
            if p1 != p2:
                st.error("Las contraseñas no coinciden.")
                st.stop()
            if (df["username"] == username).any():
                st.error("Ese usuario ya existe.")
                st.stop()

            df = pd.concat(
                [
                    df,
                    pd.DataFrame(
                        [
                            {
                                "company": company.strip(),
                                "username": username.strip(),
                                "password_hash": _hash_password(p1),
                                "role": "client",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
            save_users(df)
            st.success("Usuario creado.")

    st.divider()
    st.caption("Usuarios actuales:")
    st.dataframe(df[["company", "username", "role"]], use_container_width=True)


# =========================================================
# PORTAL UI (placeholder para ir construyendo)
# =========================================================
def portal_screen():
    auth = st.session_state["auth"]
    username = auth["username"]
    role = auth["role"]
    company_fixed = auth["company"]

    with st.sidebar:
        st.write(f"**Usuario:** {username}")
        st.write(f"**Rol:** {role}")
        if st.button("Cerrar sesión"):
            st.session_state.pop("auth", None)
            st.rerun()

        st.header("Período")
        year = st.number_input("Año", min_value=2020, max_value=2100, value=datetime.now().year, step=1)
        quarter = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])
        month_in_q = st.selectbox("Mes dentro del quarter", [1, 2, 3])

        st.header("Empresa")
        if role == "admin":
            dfu = load_users()
            companies = sorted([c for c in dfu["company"].unique().tolist() if c and c != "ALL"])
            company = st.selectbox("Seleccionar empresa", options=(companies if companies else ["(sin empresas)"]))
        else:
            company = company_fixed
            st.info(f"Empresa asignada: {company}")

    st.subheader("Portal")
    st.caption("Fase 2: acá vamos a sumar carga guiada + upload raw + validaciones.")

    # Mini prueba de guardado (dummy) para validar storage y estructura de carpetas
    dummy_value = st.text_input("Dato de prueba (dummy)", value="ok")
    if st.button("Guardar (dummy)"):
        payload = {"dummy": dummy_value}
        path = save_submission(company, username, int(year), quarter, int(month_in_q), payload)
        st.success(f"Guardado: {path}")


# =========================================================
# MAIN
# =========================================================
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    render_header()

    if "auth" not in st.session_state:
        login_screen()
        return

    # Ya autenticado
    role = st.session_state["auth"]["role"]

    tabs = st.tabs(["Portal", "Admin"])
    with tabs[0]:
        portal_screen()
    with tabs[1]:
        if role == "admin":
            admin_panel()
        else:
            st.info("Solo admin.")


if __name__ == "__main__":
    main()
