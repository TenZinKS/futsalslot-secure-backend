from flask import Blueprint, request, jsonify, current_app, g

from models import db
from models.user import User, Role
from security.password import hash_password, verify_password
from security.session import create_session, revoke_session, revoke_all_sessions
from utils.audit import log_event
from utils.auth_context import login_required
from security.bruteforce import is_locked, register_failure, reset_attempts
from security.rate_limit import check_and_increment_login_rate
from security.csrf import issue_csrf_token
from datetime import datetime, timedelta
from models.password_history import PasswordHistory
from security.password_policy import validate_password, password_strength


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _is_valid_email(email: str) -> bool:
    return isinstance(email, str) and "@" in email and len(email) <= 255


def _profile_required_fields():
    fields = current_app.config.get("PROFILE_REQUIRED_FIELDS", ["full_name", "phone_number"])
    if not isinstance(fields, (list, tuple)):
        return ["full_name", "phone_number"]
    return [f for f in fields if isinstance(f, str)]


def _is_profile_complete(user: User) -> bool:
    for field in _profile_required_fields():
        value = getattr(user, field, None)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _password_recently_used(user: User, new_password: str, history_count: int) -> bool:
    if verify_password(new_password, user.password_hash):
        return True

    if history_count <= 0:
        return False

    recent = (
        PasswordHistory.query
        .filter_by(user_id=user.id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(history_count)
        .all()
    )
    return any(verify_password(new_password, row.password_hash) for row in recent)


def _record_password_history(user: User) -> None:
    db.session.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not _is_valid_email(email):
        return jsonify(error="Invalid email"), 400
    valid, errors = validate_password(password)
    if not valid:
        return jsonify(error="Password does not meet policy", details=errors), 400

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

    allowed, retry_after = check_and_increment_login_rate()
    if not allowed:
        log_event("LOGIN_RATE_LIMIT", metadata={"email": email, "retry_after": retry_after})
        return jsonify(error="Too many login requests. Slow down.", retry_after_seconds=retry_after), 429


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

    max_age_days = current_app.config.get("PASSWORD_MAX_AGE_DAYS", 90)
    if max_age_days:
        expires_at = user.password_changed_at + timedelta(days=max_age_days)
        if datetime.utcnow() > expires_at:
            log_event("LOGIN_PASSWORD_EXPIRED", user_id=user.id)
            return jsonify(
                error="Password expired",
                password_expired=True,
                max_age_days=max_age_days,
            ), 403

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

    resp = issue_csrf_token(resp)

    log_event("LOGIN_SUCCESS", user_id=user.id, metadata={"revoked_sessions": revoked_count})
    return resp, 200


@auth_bp.post("/password_strength")
def check_password_strength():
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    return jsonify(password_strength(password)), 200


@auth_bp.get("/me")
@login_required
def me():
    return jsonify(
        id=g.user.id,
        email=g.user.email,
        roles=[r.name for r in g.user.roles],
        mfa_enabled=g.user.mfa_enabled,
        full_name=g.user.full_name,
        phone_number=g.user.phone_number,
        profile_complete=_is_profile_complete(g.user),
        profile_required_fields=_profile_required_fields(),
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


@auth_bp.post("/change_password")
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if not verify_password(current_password, g.user.password_hash):
        return jsonify(error="Invalid current password"), 401

    valid, errors = validate_password(new_password)
    if not valid:
        return jsonify(error="Password does not meet policy", details=errors), 400

    history_count = current_app.config.get("PASSWORD_HISTORY_COUNT", 2)
    if _password_recently_used(g.user, new_password, history_count):
        return jsonify(error="Password was used recently"), 400

    _record_password_history(g.user)
    g.user.password_hash = hash_password(new_password)
    g.user.password_changed_at = datetime.utcnow()

    db.session.commit()
    log_event("PASSWORD_CHANGED", user_id=g.user.id)
    return jsonify(message="Password updated"), 200


@auth_bp.get("/profile")
@login_required
def get_profile():
    return jsonify(
        full_name=g.user.full_name,
        phone_number=g.user.phone_number,
        profile_complete=_is_profile_complete(g.user),
        profile_required_fields=_profile_required_fields(),
    ), 200


@auth_bp.post("/profile")
@login_required
def update_profile():
    data = request.get_json(silent=True) or {}
    full_name = data.get("full_name")
    phone_number = data.get("phone_number")

    if full_name is not None:
        if not isinstance(full_name, str) or len(full_name.strip()) > 120:
            return jsonify(error="Invalid full_name"), 400
        g.user.full_name = full_name.strip()

    if phone_number is not None:
        if not isinstance(phone_number, str) or len(phone_number.strip()) > 30:
            return jsonify(error="Invalid phone_number"), 400
        g.user.phone_number = phone_number.strip()

    db.session.commit()
    log_event("PROFILE_UPDATE", user_id=g.user.id)
    return jsonify(
        message="Profile updated",
        profile_complete=_is_profile_complete(g.user),
        profile_required_fields=_profile_required_fields(),
    ), 200
