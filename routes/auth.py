from flask import Blueprint, request, jsonify, current_app, g

from models import db
from models.user import User, Role
from models.court import Court
from security.password import hash_password, verify_password
from security.session import create_session, revoke_session, revoke_all_sessions
from utils.audit import log_event
from utils.auth_context import login_required
from utils.blocklist import is_email_blocked
from security.bruteforce import is_locked, register_failure, reset_attempts
from security.rate_limit import check_and_increment_login_rate
from security.csrf import issue_csrf_token
from utils.roles import filter_role_names
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


def _normalize_text(value: str) -> str:
    return (value or "").strip().lower()

def _get_or_create_role(name: str) -> Role | None:
    if not name:
        return None
    role = Role.query.filter_by(name=name).first()
    if role:
        return role
    role = Role(name=name)
    db.session.add(role)
    db.session.flush()
    return role


def _register_pending_court(
    data: dict,
    event_prefix: str,
    primary_role: str | None = None,
    require_all_fields: bool = False,
    add_player_role: bool = True,
):
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    phone_number = (data.get("phone_number") or "").strip()
    court_data = data.get("court") or data.get("futsal") or {}

    if not _is_valid_email(email):
        return None, jsonify(error="Invalid email"), 400
    if is_email_blocked(email):
        log_event(f"{event_prefix}_BLOCKED_EMAIL", metadata={"email": email})
        return None, jsonify(error="Email blocked"), 403
    valid, errors = validate_password(password)
    if not valid:
        return None, jsonify(error="Password does not meet policy", details=errors), 400
    if not full_name or not phone_number:
        return None, jsonify(error="full_name and phone_number are required"), 400

    if User.query.filter_by(email=email).first():
        log_event(f"{event_prefix}_FAIL_EMAIL_EXISTS", metadata={"email": email})
        return None, jsonify(error="Email already registered"), 409
    if phone_number and User.query.filter_by(phone_number=phone_number).first():
        log_event(f"{event_prefix}_FAIL_PHONE_EXISTS", metadata={"phone_number": phone_number})
        return None, jsonify(error="Phone number already registered"), 409

    name = (court_data.get("name") or "").strip()
    location = (court_data.get("location") or "").strip()
    description = (court_data.get("description") or "").strip() or None
    maps_link = (court_data.get("maps_link") or "").strip() or None

    if not name or not location:
        return None, jsonify(error="court.name and court.location are required"), 400
    if require_all_fields:
        if not description or not maps_link:
            return None, jsonify(error="court.description and court.maps_link are required"), 400

    name_norm = _normalize_text(name)
    location_norm = _normalize_text(location)
    duplicate = (
        Court.query
        .filter(
            Court.name_normalized == name_norm,
            Court.location_normalized == location_norm,
        )
        .first()
    )
    if duplicate:
        return None, jsonify(error="Court already exists"), 409

    pw_hash = hash_password(password)
    user = User(
        email=email,
        password_hash=pw_hash,
        full_name=full_name,
        phone_number=phone_number,
    )
    db.session.add(user)
    db.session.flush()

    if add_player_role:
        player_role = _get_or_create_role("PLAYER")
        if player_role:
            user.roles.append(player_role)
    if primary_role:
        extra_role = _get_or_create_role(primary_role)
        if extra_role and extra_role not in user.roles:
            user.roles.append(extra_role)

    court = Court(
        name=name,
        location=location,
        description=description,
        maps_link=maps_link,
        name_normalized=name_norm,
        location_normalized=location_norm,
        owner_user_id=user.id,
        status="PENDING",
    )
    db.session.add(court)
    db.session.commit()

    log_event(
        f"{event_prefix}_SUCCESS",
        user_id=user.id,
        entity="court",
        entity_id=court.id,
    )

    return court, jsonify(
        message="Registration submitted. Await super admin verification.",
        court_id=court.id,
        court_status=court.status,
    ), 201


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    phone_number = (data.get("phone_number") or "").strip()

    if not _is_valid_email(email):
        return jsonify(error="Invalid email"), 400
    if is_email_blocked(email):
        log_event("REGISTER_BLOCKED_EMAIL", metadata={"email": email})
        return jsonify(error="Email blocked"), 403
    valid, errors = validate_password(password)
    if not valid:
        return jsonify(error="Password does not meet policy", details=errors), 400
    if not full_name or not phone_number:
        return jsonify(error="full_name and phone_number are required"), 400

    if User.query.filter_by(email=email).first():
        log_event("REGISTER_FAIL_EMAIL_EXISTS", metadata={"email": email})
        return jsonify(error="Email already registered"), 409
    if phone_number and User.query.filter_by(phone_number=phone_number).first():
        log_event("REGISTER_FAIL_PHONE_EXISTS", metadata={"phone_number": phone_number})
        return jsonify(error="Phone number already registered"), 409

    pw_hash = hash_password(password)

    user = User(
        email=email,
        password_hash=pw_hash,
        full_name=full_name,
        phone_number=phone_number,
    )
    db.session.add(user)
    db.session.flush()

    player_role = _get_or_create_role("PLAYER")
    if player_role:
        user.roles.append(player_role)

    db.session.commit()
    log_event("REGISTER_SUCCESS", user_id=user.id)

    return jsonify(message="Registered successfully"), 201


@auth_bp.post("/admin/register")
def register_admin():
    data = request.get_json(silent=True) or {}
    _, resp, status = _register_pending_court(
        data,
        "ADMIN_REGISTER",
        primary_role=None,
        require_all_fields=True,
        add_player_role=False,
    )
    return resp, status



@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if is_email_blocked(email):
        log_event("LOGIN_BLOCKED_EMAIL", metadata={"email": email})
        return jsonify(error="Email blocked"), 403

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

    if not any(r.name == "SUPER_ADMIN" for r in user.roles):
        pending_court = Court.query.filter_by(owner_user_id=user.id, status="PENDING").first()
        if pending_court:
            log_event("LOGIN_BLOCKED_PENDING_COURT", user_id=user.id, entity="court", entity_id=pending_court.id)
            return jsonify(
                error="Court verification pending. Please wait for approval.",
                court_status=pending_court.status,
            ), 403
        rejected_court = Court.query.filter_by(owner_user_id=user.id, status="REJECTED").first()
        if rejected_court:
            log_event("LOGIN_BLOCKED_REJECTED_COURT", user_id=user.id, entity="court", entity_id=rejected_court.id)
            return jsonify(
                error="Court registration rejected. Contact support.",
                court_status=rejected_court.status,
                rejected_reason=rejected_court.rejected_reason,
            ), 403

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


@auth_bp.post("/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    allowed, retry_after = check_and_increment_login_rate()
    if not allowed:
        log_event("ADMIN_LOGIN_RATE_LIMIT", metadata={"email": email, "retry_after": retry_after})
        return jsonify(error="Too many login requests. Slow down.", retry_after_seconds=retry_after), 429

    locked, seconds_left = is_locked(email)
    if locked:
        log_event("ADMIN_LOGIN_LOCKED", metadata={"email": email, "seconds_left": seconds_left})
        return jsonify(error="Account temporarily locked. Try again later.", retry_after_seconds=seconds_left), 429

    user = User.query.filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        fail_count, locked_now = register_failure(email)
        log_event(
            "ADMIN_LOGIN_FAIL",
            user_id=user.id if user else None,
            metadata={"email": email, "fail_count": fail_count, "locked_now": locked_now}
        )
        if locked_now:
            return jsonify(error="Too many failed attempts. Account locked.", lockout_minutes=current_app.config.get("LOCKOUT_MINUTES", 10)), 429
        return jsonify(error="Invalid credentials"), 401

    admin_roles = {"ADMIN", "SUPER_ADMIN"}
    if not any(r.name in admin_roles for r in user.roles):
        log_event("ADMIN_LOGIN_FORBIDDEN", user_id=user.id)
        return jsonify(error="Forbidden"), 403

    is_platform_admin = any(r.name in {"ADMIN", "SUPER_ADMIN"} for r in user.roles)
    if not is_platform_admin:
        pending_court = Court.query.filter_by(owner_user_id=user.id, status="PENDING").first()
        if pending_court:
            log_event("ADMIN_LOGIN_BLOCKED_PENDING_COURT", user_id=user.id, entity="court", entity_id=pending_court.id)
            return jsonify(
                error="Court verification pending. Please wait for approval.",
                court_status=pending_court.status,
            ), 403
        rejected_court = Court.query.filter_by(owner_user_id=user.id, status="REJECTED").first()
        if rejected_court:
            log_event("ADMIN_LOGIN_BLOCKED_REJECTED_COURT", user_id=user.id, entity="court", entity_id=rejected_court.id)
            return jsonify(
                error="Court registration rejected. Contact support.",
                court_status=rejected_court.status,
                rejected_reason=rejected_court.rejected_reason,
            ), 403

    max_age_days = current_app.config.get("PASSWORD_MAX_AGE_DAYS", 90)
    if max_age_days:
        expires_at = user.password_changed_at + timedelta(days=max_age_days)
        if datetime.utcnow() > expires_at:
            log_event("ADMIN_LOGIN_PASSWORD_EXPIRED", user_id=user.id)
            return jsonify(
                error="Password expired",
                password_expired=True,
                max_age_days=max_age_days,
            ), 403

    reset_attempts(email)
    revoked_count = revoke_all_sessions(user.id)

    raw_token = create_session(user.id)
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "futsalslot_session")
    max_age = current_app.config.get("SESSION_LIFETIME_SECONDS", 8 * 60 * 60)

    resp = jsonify(message="Admin login OK")
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

    log_event("ADMIN_LOGIN_SUCCESS", user_id=user.id, metadata={"revoked_sessions": revoked_count})
    return resp, 200


@auth_bp.post("/superadmin/login")
def superadmin_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if is_email_blocked(email):
        log_event("SUPERADMIN_LOGIN_BLOCKED_EMAIL", metadata={"email": email})
        return jsonify(error="Email blocked"), 403

    allowed, retry_after = check_and_increment_login_rate()
    if not allowed:
        log_event("SUPERADMIN_LOGIN_RATE_LIMIT", metadata={"email": email, "retry_after": retry_after})
        return jsonify(error="Too many login requests. Slow down.", retry_after_seconds=retry_after), 429

    locked, seconds_left = is_locked(email)
    if locked:
        log_event("SUPERADMIN_LOGIN_LOCKED", metadata={"email": email, "seconds_left": seconds_left})
        return jsonify(error="Account temporarily locked. Try again later.", retry_after_seconds=seconds_left), 429

    user = User.query.filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        fail_count, locked_now = register_failure(email)
        log_event(
            "SUPERADMIN_LOGIN_FAIL",
            user_id=user.id if user else None,
            metadata={"email": email, "fail_count": fail_count, "locked_now": locked_now}
        )
        if locked_now:
            return jsonify(error="Too many failed attempts. Account locked.", lockout_minutes=current_app.config.get("LOCKOUT_MINUTES", 10)), 429
        return jsonify(error="Invalid credentials"), 401

    if not any(r.name == "SUPER_ADMIN" for r in user.roles):
        log_event("SUPERADMIN_LOGIN_FORBIDDEN", user_id=user.id)
        return jsonify(error="Forbidden"), 403

    max_age_days = current_app.config.get("PASSWORD_MAX_AGE_DAYS", 90)
    if max_age_days:
        expires_at = user.password_changed_at + timedelta(days=max_age_days)
        if datetime.utcnow() > expires_at:
            log_event("SUPERADMIN_LOGIN_PASSWORD_EXPIRED", user_id=user.id)
            return jsonify(
                error="Password expired",
                password_expired=True,
                max_age_days=max_age_days,
            ), 403

    reset_attempts(email)

    revoked_count = revoke_all_sessions(user.id)

    raw_token = create_session(user.id)
    cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "futsalslot_session")
    max_age = current_app.config.get("SESSION_LIFETIME_SECONDS", 8 * 60 * 60)

    resp = jsonify(message="Super admin login OK")
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

    log_event("SUPERADMIN_LOGIN_SUCCESS", user_id=user.id, metadata={"revoked_sessions": revoked_count})
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
        roles=filter_role_names(g.user.roles),
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
