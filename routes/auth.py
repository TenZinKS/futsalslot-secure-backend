from flask import Blueprint, request, jsonify, current_app, g

from models import db
from models.user import User, Role
from security.password import hash_password, verify_password
from security.session import create_session, revoke_session, revoke_all_sessions
from utils.audit import log_event
from utils.auth_context import login_required
from security.bruteforce import is_locked, register_failure, reset_attempts


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _is_valid_email(email: str) -> bool:
    return isinstance(email, str) and "@" in email and len(email) <= 255


def _is_valid_password(pw: str) -> bool:
    return isinstance(pw, str) and 12 <= len(pw) <= 128


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not _is_valid_email(email):
        return jsonify(error="Invalid email"), 400
    if not _is_valid_password(password):
        return jsonify(error="Password must be at least 12 characters"), 400

    if User.query.filter_by(email=email).first():
        log_event("REGISTER_FAIL_EMAIL_EXISTS", metadata={"email": email})
        return jsonify(error="Email already registered"), 409

    pw_hash = hash_password(password)

    user = User(email=email, password_hash=pw_hash)
    db.session.add(user)
    db.session.flush()

    player_role = Role.query.filter_by(name="PLAYER").first()
    if player_role:
        user.roles.append(player_role)

    db.session.commit()
    log_event("REGISTER_SUCCESS", user_id=user.id)

    return jsonify(message="Registered successfully"), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    locked, seconds_left = is_locked(email)
    if locked:
        log_event("LOGIN_LOCKED", metadata={"email": email, "seconds_left": seconds_left})
        return jsonify(error="Account temporarily locked. Try again later.", retry_after_seconds=seconds_left), 429

    user = User.query.filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        fail_count, locked_now = register_failure(email)
        log_event(
            "LOGIN_FAIL",
            user_id=user.id if user else None,
            metadata={"email": email, "fail_count": fail_count, "locked_now": locked_now}
        )
        if locked_now:
            return jsonify(error="Too many failed attempts. Account locked.", lockout_minutes=current_app.config.get("LOCKOUT_MINUTES", 10)), 429
        return jsonify(error="Invalid credentials"), 401

    reset_attempts(email)

    # Rotate: revoke any existing sessions for this user
    revoked_count = revoke_all_sessions(user.id)

    raw_token = create_session(user.id)
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "futsalslot_session")

    max_age = current_app.config.get("SESSION_LIFETIME_SECONDS", 8 * 60 * 60)

    resp = jsonify(message="Login OK")
    resp.set_cookie(
        cookie_name,
        raw_token,
        httponly=True,
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
        samesite=current_app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        max_age=max_age,
        path="/",
    )

    log_event("LOGIN_SUCCESS", user_id=user.id, metadata={"revoked_sessions": revoked_count})
    return resp, 200


@auth_bp.get("/me")
@login_required
def me():
    return jsonify(
        id=g.user.id,
        email=g.user.email,
        roles=[r.name for r in g.user.roles],
        mfa_enabled=g.user.mfa_enabled,
    ), 200


@auth_bp.post("/logout")
@login_required
def logout():
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "futsalslot_session")
    raw_token = request.cookies.get(cookie_name)

    revoke_session(raw_token)
    log_event("LOGOUT", user_id=g.user.id)

    resp = jsonify(message="Logged out")
    resp.delete_cookie(cookie_name, path="/")
    return resp, 200


@auth_bp.post("/logout_all")
@login_required
def logout_all():
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "futsalslot_session")

    count = revoke_all_sessions(g.user.id)
    log_event("LOGOUT_ALL", user_id=g.user.id, metadata={"revoked_sessions": count})

    resp = jsonify(message="Logged out everywhere", revoked_sessions=count)
    resp.delete_cookie(cookie_name, path="/")
    return resp, 200
