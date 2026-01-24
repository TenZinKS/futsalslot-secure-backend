from functools import wraps
from flask import g, jsonify

def has_role(role_name: str) -> bool:
    user = getattr(g, "user", None)
    if not user:
        return False
    return any(r.name == role_name for r in user.roles)

def require_roles(*role_names: str):
    """
    Usage: @require_roles("ADMIN")
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", None)
            if user is None:
                return jsonify(error="Authentication required"), 401

            user_roles = {r.name for r in user.roles}
            if "SUPER_ADMIN" not in user_roles and not user_roles.intersection(set(role_names)):
                return jsonify(error="Forbidden"), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
