from flask import Blueprint, request, jsonify, g

from models import db
from models.court import Court
from models.support_message import SupportMessage
from utils.auth_context import login_required
from utils.audit import log_event

court_bp = Blueprint("court", __name__, url_prefix="/courts")


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


@court_bp.post("/register")
@login_required
def register_court():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip()
    description = (data.get("description") or "").strip() or None
    maps_link = (data.get("maps_link") or "").strip() or None

    if not name or not location:
        return jsonify(error="name and location are required"), 400
    if maps_link and Court.query.filter_by(maps_link=maps_link).first():
        return jsonify(error="maps_link already used"), 409

    name_norm = _normalize(name)
    location_norm = _normalize(location)
    duplicate = (
        Court.query
        .filter(
            Court.name_normalized == name_norm,
            Court.location_normalized == location_norm,
        )
        .first()
    )
    if duplicate:
        return jsonify(error="Court already exists"), 409

    court = Court(
        name=name,
        location=location,
        description=description,
        maps_link=maps_link,
        name_normalized=name_norm,
        location_normalized=location_norm,
        owner_user_id=g.user.id,
        status="PENDING",
    )
    db.session.add(court)
    db.session.commit()

    log_event("COURT_REGISTER_SUBMIT", user_id=g.user.id, entity="court", entity_id=court.id)
    return jsonify(id=court.id, status=court.status), 201


@court_bp.post("")
@login_required
def register_court_alias():
    return register_court()


@court_bp.get("/me")
@login_required
def my_courts():
    courts = (
        Court.query
        .filter_by(owner_user_id=g.user.id)
        .order_by(Court.created_at.desc())
        .all()
    )
    if not courts:
        return jsonify(error="No court registration found"), 404
    return jsonify([
        {
            "id": court.id,
            "name": court.name,
            "location": court.location,
            "description": court.description,
            "maps_link": court.maps_link,
            "status": court.status,
            "created_at": court.created_at.isoformat(),
            "verified_at": court.verified_at.isoformat() if court.verified_at else None,
            "rejected_reason": court.rejected_reason,
        }
        for court in courts
    ]), 200


@court_bp.get("")
def list_public_courts():
    status = (request.args.get("status") or "VERIFIED").strip().upper()
    name_query = (request.args.get("name") or "").strip()
    location_query = (request.args.get("location") or "").strip()

    q = Court.query.filter(Court.is_active.is_(True))
    if status:
        q = q.filter(Court.status == status)
    if name_query:
        like = f"%{name_query}%"
        q = q.filter(Court.name.ilike(like))
    if location_query:
        q = q.filter(Court.location.ilike(f"%{location_query}%"))

    rows = q.order_by(Court.created_at.desc()).limit(200).all()
    return jsonify([
        {
            "id": c.id,
            "name": c.name,
            "location": c.location,
            "description": c.description,
            "maps_link": c.maps_link,
            "status": c.status,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]), 200


@court_bp.post("/<int:court_id>/support-messages")
@login_required
def create_support_message(court_id: int):
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    subject = (data.get("subject") or "").strip() or None
    if not message:
        return jsonify(error="message is required"), 400

    court = Court.query.get(court_id)
    if not court:
        return jsonify(error="Court not found"), 404

    msg = SupportMessage(
        user_id=g.user.id,
        court_id=court.id,
        subject=subject,
        message=message,
        status="OPEN",
    )
    db.session.add(msg)
    db.session.commit()

    log_event("COURT_SUPPORT_MESSAGE_CREATE", user_id=g.user.id, entity="support_message", entity_id=msg.id)
    return jsonify(id=msg.id, status=msg.status), 201
