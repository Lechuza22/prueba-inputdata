import hashlib
import pandas as pd
from .config import USERS_FILE

def _hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()

def _verify_password(plain: str, hashed: str) -> bool:
    return _hash_password(plain) == (hashed or "")

def load_users() -> pd.DataFrame:
    if not USERS_FILE.exists():
        df = pd.DataFrame(columns=["company","username","password_hash","role"])
        df.to_csv(USERS_FILE, index=False)

    df = pd.read_csv(USERS_FILE)
    for col in ["company","username","password_hash","role"]:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    return df

def save_users(df: pd.DataFrame) -> None:
    df.to_csv(USERS_FILE, index=False)

def ensure_admin() -> None:
    df = load_users()
    exists = ((df["username"]=="admin") & (df["role"]=="admin")).any()
    if not exists:
        df = pd.concat([df, pd.DataFrame([{
            "company":"ALL","username":"admin","password_hash":"","role":"admin"
        }])], ignore_index=True)
        save_users(df)
