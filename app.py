import streamlit as st
from config import APP_TITLE
from ui.login import render_login

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)

    if "auth" not in st.session_state:
        render_login()
    else:
        a = st.session_state["auth"]
        st.success(f"Logueado como {a['username']} • rol: {a['role']} • empresa: {a['company']}")
        if st.button("Cerrar sesión"):
            st.session_state.pop("auth", None)
            st.rerun()

if __name__ == "__main__":
    main()
