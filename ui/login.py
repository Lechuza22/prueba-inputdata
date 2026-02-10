import streamlit as st
from auth import load_users, save_users, ensure_admin, _hash_password, _verify_password

def render_login():
    ensure_admin()
    df = load_users()

    st.subheader("Login")

    # si admin sin password, setear
    admin = df[(df.username=="admin") & (df.role=="admin")].head(1)
    if not admin.empty and admin.iloc[0]["password_hash"] == "":
        st.warning("Primera vez: configurá contraseña del admin.")
        p1 = st.text_input("Nueva contraseña admin", type="password")
        p2 = st.text_input("Repetir contraseña", type="password")
        if st.button("Guardar contraseña"):
            if not p1 or len(p1) < 8:
                st.error("Min 8 caracteres.")
                st.stop()
            if p1 != p2:
                st.error("No coinciden.")
                st.stop()
            idx = admin.index[0]
            df.loc[idx,"password_hash"] = _hash_password(p1)
            save_users(df)
            st.success("Listo. Ahora logueate.")
            st.rerun()

    user = st.text_input("Usuario")
    pwd = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):
        row = df[df.username==user].head(1)
        if row.empty:
            st.error("Usuario no encontrado.")
            return
        if not _verify_password(pwd, row.iloc[0]["password_hash"]):
            st.error("Contraseña incorrecta.")
            return

        st.session_state["auth"] = {
            "username": user,
            "role": row.iloc[0]["role"],
            "company": row.iloc[0]["company"],
        }
        st.rerun()
