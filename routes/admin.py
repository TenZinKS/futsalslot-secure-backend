from datetime import datetime, timedelta
from flask import Blueprint, jsonify, g, request, current_app
from security.rbac import require_roles
from utils.audit import log_event
from models import db
from models.user import User, Role
from models.court import Court
from models.slot import Slot
from models.booking import Booking
from models.blocked_email import BlockedEmail
from utils.emailer import send_email
from utils.blocklist import normalize_email
from utils.roles import filter_role_names

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

def _get_courts_for_admin(user):
    if not user:
        return []
    return (
        Court.query
        .filter_by(owner_user_id=user.id)
        .order_by(Court.created_at.desc())
        .all()
    )

@admin_bp.get("/dashboard")
@require_roles("ADMIN")
def dashboard():
    log_event("ADMIN_DASHBOARD_VIEW", user_id=g.user.id)
    return jsonify(message="Welcome to staff/admin dashboard"), 200


@admin_bp.get("/courts/dashboard")
@require_roles("ADMIN")
def admin_courts_dashboard():
    courts = _get_courts_for_admin(g.user)
    if not courts:
        return jsonify(error="No court registration found"), 404

    court_ids = [c.id for c in courts]
    slot_count = Slot.query.filter(Slot.court_id.in_(court_ids)).count() if court_ids else 0
    booking_count = (
        Booking.query
        .join(Slot, Booking.slot_id == Slot.id)
        .join(Court, Slot.court_id == Court.id)
        .filter(Court.id.in_(court_ids))
        .count()
    )

    log_event("ADMIN_COURT_DASHBOARD_VIEW", user_id=g.user.id)
    return jsonify(
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
        stats={
            "courts": len(courts),
            "slots": slot_count,
            "bookings": booking_count,
        },
    ), 200


@admin_bp.get("/courts/bookings")
@require_roles("ADMIN")
def admin_courts_bookings():
    courts = _get_courts_for_admin(g.user)
    if not courts:
        return jsonify(error="No court registration found"), 404
    court_ids = [c.id for c in courts]

    status = request.args.get("status")
    date_str = request.args.get("date")  # YYYY-MM-DD

    q = (
        Booking.query
        .join(Slot, Booking.slot_id == Slot.id)
        .join(Court, Slot.court_id == Court.id)
        .filter(Court.id.in_(court_ids))
    )

    if status:
        q = q.filter(Booking.status == status)

    if date_str:
        try:
            day = datetime.fromisoformat(date_str)
        except Exception:
            return jsonify(error="Invalid date. Use YYYY-MM-DD"), 400
        start = datetime(day.year, day.month, day.day)
        end = start + timedelta(days=1)
        q = q.filter(Slot.start_time >= start, Slot.start_time < end)

    rows = q.order_by(Booking.created_at.desc()).limit(200).all()
    log_event("ADMIN_COURT_BOOKINGS_VIEW", user_id=g.user.id)
    return jsonify([
        {
            "id": b.id,
            "slot_id": b.slot_id,
            "user_id": b.user_id,
            "status": b.status,
            "created_at": b.created_at.isoformat(),
        }
        for b in rows
    ]), 200


@admin_bp.get("/users")
@require_roles("ADMIN")
def list_users():
    role_filter = (request.args.get("role") or "").strip().upper()
    q = User.query
    if role_filter:
        q = q.join(User.roles).filter(Role.name == role_filter)

    users = q.order_by(User.created_at.desc()).limit(200).all()
    blocked = {b.email_normalized for b in BlockedEmail.query.all()}
    return jsonify([
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "phone_number": u.phone_number,
            "roles": filter_role_names(u.roles),
            "created_at": u.created_at.isoformat(),
            "blocked": normalize_email(u.email) in blocked,
        }
        for u in users
    ]), 200


@admin_bp.post("/users/<int:user_id>/roles")
@require_roles("ADMIN")
def update_user_roles(user_id: int):
    data = request.get_json(silent=True) or {}
    roles = data.get("roles")
    if not isinstance(roles, list) or not roles:
        return jsonify(error="roles must be a non-empty list"), 400

    role_names = []
    for name in roles:
        if isinstance(name, str) and name.strip():
            role_names.append(name.strip().upper())
    if not role_names:
        return jsonify(error="roles must include valid role names"), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify(error="User not found"), 404

    available_roles = Role.query.filter(Role.name.in_(set(role_names))).all()
    available_names = {r.name for r in available_roles}
    missing = set(role_names) - available_names
    if missing:
        return jsonify(error="Unknown role(s)", missing=sorted(missing)), 400

    if user.id == g.user.id and "ADMIN" not in role_names:
        return jsonify(error="Cannot remove your own ADMIN role"), 403

    if "ADMIN" not in role_names and any(r.name == "ADMIN" for r in user.roles):
        admin_count = User.query.join(User.roles).filter(Role.name == "ADMIN").count()
        if admin_count <= 1:
            return jsonify(error="Cannot remove the last ADMIN"), 403

    user.roles = available_roles
    db.session.commit()

    log_event(
        "ADMIN_UPDATE_ROLES",
        user_id=g.user.id,
        entity="user",
        entity_id=user.id,
        metadata={"roles": role_names},
    )

    return jsonify(message="Roles updated", roles=filter_role_names(role_names)), 200


@admin_bp.get("/courts")
@require_roles("SUPER_ADMIN")
def list_courts():
    status = (request.args.get("status") or "").strip().upper()
    q = Court.query
    if status:
        q = q.filter(Court.status == status)

    rows = q.order_by(Court.created_at.desc()).limit(200).all()
    return jsonify([
        {
            "id": f.id,
            "name": f.name,
            "location": f.location,
            "status": f.status,
            "owner_user_id": f.owner_user_id,
            "created_at": f.created_at.isoformat(),
            "verified_at": f.verified_at.isoformat() if f.verified_at else None,
            "rejected_reason": f.rejected_reason,
        }
        for f in rows
    ]), 200


@admin_bp.post("/courts/<int:court_id>/verify")
@require_roles("SUPER_ADMIN")
def verify_court(court_id: int):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip().upper()
    reason = (data.get("reason") or "").strip() or None

    if status not in ("VERIFIED", "REJECTED"):
        return jsonify(error="status must be VERIFIED or REJECTED"), 400

    court = Court.query.get(court_id)
    if not court:
        return jsonify(error="Court not found"), 404

    court.status = status
    court.verified_by = g.user.id
    court.verified_at = datetime.utcnow()
    court.rejected_reason = reason if status == "REJECTED" else None

    if status == "VERIFIED":
        owner = User.query.get(court.owner_user_id)
        if owner:
            admin_role = Role.query.filter_by(name="ADMIN").first()
            if admin_role:
                owner.roles = [admin_role]
            else:
                admin_role = Role(name="ADMIN")
                db.session.add(admin_role)
                db.session.flush()
                owner.roles = [admin_role]
    if status == "REJECTED":
        owner = User.query.get(court.owner_user_id)
        if owner:
            has_other_verified = (
                Court.query
                .filter(
                    Court.owner_user_id == owner.id,
                    Court.status == "VERIFIED",
                    Court.id != court.id,
                )
                .first()
                is not None
            )
            # Only remove ADMIN if this was their first (new) court verification attempt.
            if not has_other_verified:
                owner.roles = [r for r in owner.roles if r.name != "ADMIN"]

    db.session.commit()

    if status == "VERIFIED":
        owner = User.query.get(court.owner_user_id)
        if owner:
            dashboard_url = current_app.config.get("ADMIN_DASHBOARD_URL") or ""
            link_line = f"\n\nLogin here: {dashboard_url}" if dashboard_url else ""
            subject = "Your court has been verified"
            body = (
                f"Hi {owner.full_name or owner.email},\n\n"
                f"Your court '{court.name}' has been verified. "
                "Welcome to FutsalSlot! You can now log in, manage slots, and manage bookings."
                f"{link_line}\n\n"
                "Thank you,\nFutsalSlot"
            )
            ok, error = send_email(owner.email, subject, body)
            log_event(
                "SUPER_ADMIN_COURT_VERIFICATION_EMAIL",
                user_id=g.user.id,
                entity="court",
                entity_id=court.id,
                metadata={"sent": ok, "error": error},
            )

    log_event(
        "ADMIN_COURT_VERIFY",
        user_id=g.user.id,
        entity="court",
        entity_id=court.id,
        metadata={"status": status, "reason": reason},
    )

    return jsonify(message="Court updated", status=status), 200
