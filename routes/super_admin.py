from flask import Blueprint, jsonify, g, request

from security.rbac import require_roles
from models import db
from models.blocked_email import BlockedEmail
from utils.blocklist import normalize_email
from utils.audit import log_event
from models.court import Court
from models.user import User, Role
from models.support_message import SupportMessage
from utils.roles import filter_role_names

super_admin_bp = Blueprint("super_admin", __name__, url_prefix="/super-admin")


@super_admin_bp.get("/dashboard")
@require_roles("SUPER_ADMIN")
def dashboard():
    log_event("SUPER_ADMIN_DASHBOARD_VIEW", user_id=g.user.id)
    return jsonify(message="Welcome to super admin dashboard"), 200


@super_admin_bp.get("/requests")
@require_roles("SUPER_ADMIN")
def list_requests():
    status = (request.args.get("status") or "PENDING").strip().upper()
    q = Court.query
    if status:
        q = q.filter(Court.status == status)

    rows = q.order_by(Court.created_at.desc()).limit(200).all()
    owner_ids = [f.owner_user_id for f in rows]
    owners = {u.id: u for u in User.query.filter(User.id.in_(owner_ids)).all()} if owner_ids else {}

    return jsonify([
        {
            "court": {
                "id": f.id,
                "name": f.name,
                "location": f.location,
                "description": f.description,
                "maps_link": f.maps_link,
                "status": f.status,
                "created_at": f.created_at.isoformat(),
            },
            "owner": {
                "id": owners.get(f.owner_user_id).id if owners.get(f.owner_user_id) else None,
                "email": owners.get(f.owner_user_id).email if owners.get(f.owner_user_id) else None,
                "full_name": owners.get(f.owner_user_id).full_name if owners.get(f.owner_user_id) else None,
                "phone_number": owners.get(f.owner_user_id).phone_number if owners.get(f.owner_user_id) else None,
            },
        }
        for f in rows
    ]), 200


@super_admin_bp.get("/admins")
@require_roles("SUPER_ADMIN")
def list_admins():
    owners = (
        User.query
        .join(User.roles)
        .filter(Role.name.in_(["SUPER_ADMIN", "ADMIN"]))
        .order_by(User.created_at.desc())
        .limit(200)
        .all()
    )
    visible = []
    for u in owners:
        role_names = {r.name for r in u.roles}
        if "SUPER_ADMIN" in role_names:
            visible.append(u)
            continue
        verified = Court.query.filter_by(owner_user_id=u.id, status="VERIFIED").first()
        if verified:
            visible.append(u)
    return jsonify([
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "phone_number": u.phone_number,
            "roles": filter_role_names(u.roles),
            "created_at": u.created_at.isoformat(),
        }
        for u in visible
    ]), 200


@super_admin_bp.get("/admins/<int:user_id>")
@require_roles("SUPER_ADMIN")
def admin_detail(user_id: int):
    user = User.query.get(user_id)
    if not user:
        return jsonify(error="User not found"), 404

    courts = Court.query.filter_by(owner_user_id=user.id).order_by(Court.created_at.desc()).all()

    return jsonify(
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "roles": filter_role_names(user.roles),
        },
        courts=[
            {
                "id": c.id,
                "name": c.name,
                "location": c.location,
                "description": c.description,
                "maps_link": c.maps_link,
                "is_active": c.is_active,
                "status": c.status,
                "created_at": c.created_at.isoformat(),
                "verified_at": c.verified_at.isoformat() if c.verified_at else None,
                "rejected_reason": c.rejected_reason,
            }
            for c in courts
        ],
    ), 200


@super_admin_bp.get("/blocked-emails")
@require_roles("SUPER_ADMIN")
def list_blocked_emails():
    rows = BlockedEmail.query.order_by(BlockedEmail.created_at.desc()).limit(200).all()
    return jsonify([
        {
            "id": r.id,
            "email": r.email,
            "reason": r.reason,
            "blocked_by": r.blocked_by,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]), 200


@super_admin_bp.post("/blocked-emails")
@require_roles("SUPER_ADMIN")
def block_email():
    data = request.get_json(silent=True) or {}
    raw_email = (data.get("email") or "").strip()
    email_norm = normalize_email(raw_email)
    if not email_norm or "@" not in email_norm:
        return jsonify(error="Invalid email"), 400

    super_admin_user = User.query.filter_by(email=email_norm).first()
    if super_admin_user and any(r.name == "SUPER_ADMIN" for r in super_admin_user.roles):
        return jsonify(error="Cannot block a SUPER_ADMIN email"), 403

    if BlockedEmail.query.filter_by(email_normalized=email_norm).first():
        return jsonify(error="Email already blocked"), 409

    reason = (data.get("reason") or "").strip() or None
    row = BlockedEmail(
        email=raw_email,
        email_normalized=email_norm,
        reason=reason,
        blocked_by=g.user.id,
    )
    db.session.add(row)
    db.session.commit()

    log_event(
        "SUPER_ADMIN_BLOCK_EMAIL",
        user_id=g.user.id,
        entity="blocked_email",
        entity_id=row.id,
        metadata={"email": raw_email, "reason": reason},
    )

    return jsonify(id=row.id, email=row.email, reason=row.reason), 201


@super_admin_bp.delete("/blocked-emails/<int:block_id>")
@require_roles("SUPER_ADMIN")
def unblock_email(block_id: int):
    row = BlockedEmail.query.get(block_id)
    if not row:
        return jsonify(error="Not found"), 404

    db.session.delete(row)
    db.session.commit()

    log_event(
        "SUPER_ADMIN_UNBLOCK_EMAIL",
        user_id=g.user.id,
        entity="blocked_email",
        entity_id=block_id,
        metadata={"email": row.email},
    )

    return jsonify(message="Unblocked"), 200


@super_admin_bp.post("/courts/<int:court_id>/block")
@require_roles("SUPER_ADMIN")
def block_court(court_id: int):
    court = Court.query.get(court_id)
    if not court:
        return jsonify(error="Court not found"), 404

    court.is_active = False
    db.session.commit()

    log_event("SUPER_ADMIN_BLOCK_COURT", user_id=g.user.id, entity="court", entity_id=court.id)
    return jsonify(message="Court blocked", id=court.id, is_active=court.is_active), 200


@super_admin_bp.post("/courts/<int:court_id>/unblock")
@require_roles("SUPER_ADMIN")
def unblock_court(court_id: int):
    court = Court.query.get(court_id)
    if not court:
        return jsonify(error="Court not found"), 404

    court.is_active = True
    db.session.commit()

    log_event("SUPER_ADMIN_UNBLOCK_COURT", user_id=g.user.id, entity="court", entity_id=court.id)
    return jsonify(message="Court unblocked", id=court.id, is_active=court.is_active), 200


@super_admin_bp.get("/support-messages")
@require_roles("SUPER_ADMIN")
def list_support_messages():
    status = (request.args.get("status") or "OPEN").strip().upper()
    q = SupportMessage.query
    if status:
        q = q.filter(SupportMessage.status == status)

    rows = q.order_by(SupportMessage.created_at.desc()).limit(200).all()
    court_ids = [r.court_id for r in rows if r.court_id]
    user_ids = [r.user_id for r in rows if r.user_id]
    courts = {c.id: c for c in Court.query.filter(Court.id.in_(court_ids)).all()} if court_ids else {}
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return jsonify([
        {
            "id": r.id,
            "subject": r.subject,
            "message": r.message,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "court": {
                "id": courts.get(r.court_id).id if courts.get(r.court_id) else None,
                "name": courts.get(r.court_id).name if courts.get(r.court_id) else None,
                "location": courts.get(r.court_id).location if courts.get(r.court_id) else None,
            },
            "user": {
                "id": users.get(r.user_id).id if users.get(r.user_id) else None,
                "email": users.get(r.user_id).email if users.get(r.user_id) else None,
                "full_name": users.get(r.user_id).full_name if users.get(r.user_id) else None,
                "phone_number": users.get(r.user_id).phone_number if users.get(r.user_id) else None,
            },
        }
        for r in rows
    ]), 200


@super_admin_bp.post("/support-messages/<int:msg_id>/status")
@require_roles("SUPER_ADMIN")
def update_support_message_status(msg_id: int):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip().upper()
    if status not in ("OPEN", "CLOSED"):
        return jsonify(error="status must be OPEN or CLOSED"), 400

    msg = SupportMessage.query.get(msg_id)
    if not msg:
        return jsonify(error="Not found"), 404

    msg.status = status
    db.session.commit()

    log_event(
        "SUPER_ADMIN_SUPPORT_STATUS",
        user_id=g.user.id,
        entity="support_message",
        entity_id=msg.id,
        metadata={"status": status},
    )

    return jsonify(message="Updated", status=status), 200


def _list_user_courts(user_id: int):
    courts = Court.query.filter_by(owner_user_id=user_id).order_by(Court.created_at.desc()).all()
    return jsonify([
        {
            "id": c.id,
            "name": c.name,
            "location": c.location,
            "description": c.description,
            "maps_link": c.maps_link,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat(),
            "status": c.status,
        }
        for c in courts
    ]), 200


@super_admin_bp.get("/owners/<int:user_id>/courts")
@require_roles("SUPER_ADMIN")
def list_owner_courts(user_id: int):
    return _list_user_courts(user_id)


@super_admin_bp.get("/admins/<int:user_id>/courts")
@require_roles("SUPER_ADMIN")
def list_admin_courts(user_id: int):
    return _list_user_courts(user_id)


@super_admin_bp.post("/courts/<int:court_id>/status")
@require_roles("SUPER_ADMIN")
def update_court_status(court_id: int):
    data = request.get_json(silent=True) or {}
    active = data.get("is_active")
    if active is None:
        return jsonify(error="is_active is required"), 400

    court = Court.query.get(court_id)
    if not court:
        return jsonify(error="Court not found"), 404

    court.is_active = bool(active)
    db.session.commit()

    log_event(
        "SUPER_ADMIN_COURT_STATUS",
        user_id=g.user.id,
        entity="court",
        entity_id=court.id,
        metadata={"is_active": court.is_active},
    )

    return jsonify(message="Updated", is_active=court.is_active), 200
