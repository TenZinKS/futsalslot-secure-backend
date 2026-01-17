import secrets
from flask import request, jsonify, current_app

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

def issue_csrf_token(resp):
    token = secrets.token_urlsafe(32)
    resp.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,  # must be readable by client JS
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
        samesite=current_app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        path="/",
    )
    return resp

def require_csrf():
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    if not cookie_token or not header_token or cookie_token != header_token:
        return jsonify(error="CSRF validation failed"), 403
    return None
