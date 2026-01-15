from functools import wraps
from flask import g, jsonify
from security.session import get_session_from_request
from models.user import User

def load_current_user():
    sess = get_session_from_request()
    if not sess:
        g.user = None
        g.session = None
        return
    g.session = sess
    g.user = User.query.get(sess.user_id)

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(g, "user", None) is None:
            return jsonify(error="Authentication required"), 401
        return fn(*args, **kwargs)
    return wrapper
