import bcrypt

def hash_password(plain_password: str) -> str:
    if not isinstance(plain_password, str) or len(plain_password) == 0:
        raise ValueError("Password must be a non-empty string")

    # bcrypt expects bytes
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, password_hash: str) -> bool:
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8")
        )
    except Exception:
        return False
