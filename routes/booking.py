from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from flask import Blueprint, request, jsonify, current_app, g
from models import db
from models.court import Court
from models.slot import Slot
from models.booking import Booking
from models.user import User
from models.payment import Payment
from security.rbac import require_roles, has_role
from utils.auth_context import login_required
from utils.audit import log_event

booking_bp = Blueprint("booking", __name__)

def _parse_iso(dt_str: str):
    # Expect ISO format like "2026-01-20T18:00:00"
    return datetime.fromisoformat(dt_str)



def _profile_required_fields():
    fields = current_app.config.get("PROFILE_REQUIRED_FIELDS", ["full_name", "phone_number"])
    if not isinstance(fields, (list, tuple)):
        return ["full_name", "phone_number"]
    return [f for f in fields if isinstance(f, str)]


def _is_profile_complete(user) -> bool:
    for field in _profile_required_fields():
        value = getattr(user, field, None)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _get_verified_courts_for_user(user):
    if not user:
        return []
    return (
        Court.query
        .filter_by(owner_user_id=user.id, status="VERIFIED")
        .order_by(Court.created_at.desc())
        .all()
    )

# ---------- ADMIN: manage courts ----------
@booking_bp.post("/booking/courts")
@login_required
def create_court():
    if not has_role("ADMIN"):
        return jsonify(error="Forbidden"), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip() or None
    description = (data.get("description") or "").strip()
    maps_link = (data.get("maps_link") or "").strip() or None
    owner_user_id = data.get("owner_user_id") if has_role("ADMIN") else None
    if owner_user_id is None:
        owner_user_id = g.user.id

    if not name:
        return jsonify(error="Court name required"), 400
    if not location:
        return jsonify(error="Court location required"), 400
    if not description:
        return jsonify(error="Court description required"), 400
    if maps_link and Court.query.filter_by(maps_link=maps_link).first():
        return jsonify(error="maps_link already used"), 409
    name_norm = (name or "").strip().lower()
    location_norm = (location or "").strip().lower()
    c = Court(
        name=name,
        location=location,
        description=description,
        maps_link=maps_link,
        name_normalized=name_norm,
        location_normalized=location_norm,
        owner_user_id=owner_user_id,
        status="PENDING",
    )
    db.session.add(c)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Court already exists"), 409

    log_event("COURT_CREATE", user_id=g.user.id, entity="court", entity_id=c.id)
    return jsonify(
        id=c.id,
        name=c.name,
        location=c.location,
        description=c.description,
        maps_link=c.maps_link,
    ), 201


@booking_bp.get("/booking/courts")
@login_required
def list_courts():
    owner_user_id = request.args.get("owner_user_id", type=int)
    location_query = (request.args.get("location") or "").strip()
    q = (
        Court.query
        .filter(Court.is_active.is_(True), Court.status == "VERIFIED")
    )
    if owner_user_id:
        q = q.filter(Court.owner_user_id == owner_user_id)
    if location_query:
        q = q.filter(Court.location.ilike(f"%{location_query}%"))

    courts = q.all()
    out = []
    for c in courts:
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "location": c.location,
                "description": c.description,
                "maps_link": c.maps_link,
            }
        )

    return jsonify(out), 200


@booking_bp.get("/booking/public/courts")
def list_public_courts():
    owner_user_id = request.args.get("owner_user_id", type=int)
    location_query = (request.args.get("location") or "").strip()
    q = (
        Court.query
        .filter(Court.is_active.is_(True), Court.status == "VERIFIED")
    )
    if owner_user_id:
        q = q.filter(Court.owner_user_id == owner_user_id)
    if location_query:
        q = q.filter(Court.location.ilike(f"%{location_query}%"))

    courts = q.all()
    out = []
    for c in courts:
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "location": c.location,
                "description": c.description,
                "maps_link": c.maps_link,
            }
        )

    return jsonify(out), 200


@booking_bp.get("/public/courts")
def list_public_courts_alias():
    return list_public_courts()


# ---------- ADMIN: create slots ----------
@booking_bp.post("/slots")
@login_required
def create_slot():
    data = request.get_json(silent=True) or {}
    court_id = data.get("court_id")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    price = int(data.get("price") or 0)

    if not court_id or not start_time or not end_time:
        return jsonify(error="court_id, start_time, end_time are required"), 400

    try:
        st = _parse_iso(start_time)
        et = _parse_iso(end_time)
    except Exception:
        return jsonify(error="Invalid datetime format. Use ISO e.g. 2026-01-20T18:00:00"), 400

    if et <= st:
        return jsonify(error="end_time must be after start_time"), 400

    court = Court.query.get(court_id)
    if not court or not court.is_active:
        return jsonify(error="Court not found"), 404
    if court.status != "VERIFIED":
        return jsonify(error="Court not verified"), 403

    if not has_role("ADMIN"):
        if court.owner_user_id != g.user.id:
            return jsonify(error="Forbidden"), 403

    slot = Slot(court_id=court_id, start_time=st, end_time=et, price=price)
    db.session.add(slot)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Slot already exists for that court and time"), 409

    log_event("SLOT_CREATE", user_id=g.user.id, entity="slot", entity_id=slot.id)
    return jsonify(id=slot.id), 201


# ---------- PLAYERS: view slots ----------
@booking_bp.get("/slots")
@login_required
def list_slots():
    # optional filters: court_id, date (YYYY-MM-DD)
    court_id = request.args.get("court_id", type=int)
    date_str = request.args.get("date")

    q = (
        Slot.query
        .join(Court, Slot.court_id == Court.id)
        .filter(Slot.is_active.is_(True), Court.status == "VERIFIED")
    )
    if court_id:
        q = q.filter(Slot.court_id == court_id)

    if date_str:
        try:
            day = datetime.fromisoformat(date_str)
        except Exception:
            return jsonify(error="Invalid date. Use YYYY-MM-DD"), 400
        start = datetime(day.year, day.month, day.day)
        end = start + timedelta(days=1)
        q = q.filter(Slot.start_time >= start, Slot.start_time < end)

    slots = q.order_by(Slot.start_time.asc()).all()

    # mark availability: slot is NOT available if there is a CONFIRMED booking
    slot_ids = [s.id for s in slots]
    booked = set(
        r.slot_id for r in Booking.query.filter(
            Booking.slot_id.in_(slot_ids),
            Booking.status == "CONFIRMED"
        ).all()
    )

    return jsonify([
        {
            "id": s.id,
            "court_id": s.court_id,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "price": s.price,
            "available": (s.id not in booked)
        }
        for s in slots
    ]), 200


@booking_bp.get("/public/slots")
def list_public_slots():
    court_id = request.args.get("court_id", type=int)
    date_str = request.args.get("date")

    q = (
        Slot.query
        .join(Court, Slot.court_id == Court.id)
        .filter(Slot.is_active.is_(True), Court.status == "VERIFIED")
    )
    if court_id:
        q = q.filter(Slot.court_id == court_id)

    if date_str:
        try:
            day = datetime.fromisoformat(date_str)
        except Exception:
            return jsonify(error="Invalid date. Use YYYY-MM-DD"), 400
        start = datetime(day.year, day.month, day.day)
        end = start + timedelta(days=1)
        q = q.filter(Slot.start_time >= start, Slot.start_time < end)

    slots = q.order_by(Slot.start_time.asc()).all()
    slot_ids = [s.id for s in slots]
    booked = set(
        r.slot_id for r in Booking.query.filter(
            Booking.slot_id.in_(slot_ids),
            Booking.status == "CONFIRMED"
        ).all()
    )

    return jsonify([
        {
            "id": s.id,
            "court_id": s.court_id,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "price": s.price,
            "available": (s.id not in booked)
        }
        for s in slots
    ]), 200


# ---------- PLAYERS: book slot (DOUBLE-BOOKING SAFE) ----------
@booking_bp.post("/bookings")
@login_required
def create_booking():
    return jsonify(
        error="Use /payments/start with slot_id to book and pay",
        details="Bookings are created only after successful payment.",
    ), 400


# ---------- PLAYERS: cancel booking ----------
@booking_bp.post("/bookings/<int:booking_id>/cancel")
@login_required
def cancel_booking(booking_id: int):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip() or None

    booking = Booking.query.get(booking_id)
    if not booking or booking.user_id != g.user.id:
        return jsonify(error="Booking not found"), 404

    if booking.status != "CONFIRMED":
        return jsonify(error="Booking not cancellable"), 400

    # If booking is CONFIRMED, apply cutoff policy
    if booking.status == "CONFIRMED":
        slot = Slot.query.get(booking.slot_id)
        cutoff_hours = current_app.config.get("CANCEL_CUTOFF_HOURS", 12)
        if slot and (slot.start_time - datetime.utcnow()).total_seconds() < cutoff_hours * 3600:
            return jsonify(error=f"Cancellation not allowed within {cutoff_hours} hours of start"), 403

    payment = Payment.query.filter_by(booking_id=booking.id).first()

    booking.status = "CANCELLED"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = reason
    if payment:
        payment.status = "FAILED"
        db.session.delete(payment)
    db.session.delete(booking)
    db.session.commit()

    log_event("BOOKING_CANCEL", user_id=g.user.id, entity="booking", entity_id=booking_id, metadata={"reason": reason})
    return jsonify(message="Cancelled"), 200


# ---------- PLAYERS: view my bookings ----------
@booking_bp.get("/bookings/me")
@login_required
def my_bookings():
    status = request.args.get("status")  # CONFIRMED/CANCELLED
    q = Booking.query.filter_by(user_id=g.user.id)
    if status:
        q = q.filter_by(status=status)

    rows = q.order_by(Booking.created_at.desc()).all()

    slot_ids = [b.slot_id for b in rows]
    slots = {s.id: s for s in Slot.query.filter(Slot.id.in_(slot_ids)).all()}

    out = []
    for b in rows:
        s = slots.get(b.slot_id)
        out.append({
            "id": b.id,
            "status": b.status,
            "created_at": b.created_at.isoformat(),
            "cancelled_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
            "slot": {
                "slot_id": b.slot_id,
                "court_id": s.court_id if s else None,
                "start_time": s.start_time.isoformat() if s else None,
                "end_time": s.end_time.isoformat() if s else None,
                "price": s.price if s else None,
            }
        })
    return jsonify(out), 200


# ---------- ADMIN: deactivate slot ----------
@booking_bp.post("/slots/<int:slot_id>/deactivate")
@login_required
def deactivate_slot(slot_id: int):
    slot = Slot.query.get(slot_id)
    if not slot:
        return jsonify(error="Slot not found"), 404
    court = Court.query.get(slot.court_id)
    if not court:
        return jsonify(error="Court not found"), 404

    if not has_role("ADMIN"):
        if court.owner_user_id != g.user.id:
            return jsonify(error="Forbidden"), 403

    slot.is_active = False
    db.session.commit()

    log_event("SLOT_DEACTIVATE", user_id=g.user.id, entity="slot", entity_id=slot_id)
    return jsonify(message="Slot deactivated"), 200


# ---------- ADMIN: list all bookings ----------
@booking_bp.get("/bookings")
@login_required
def list_all_bookings():
    status = request.args.get("status")
    q = Booking.query
    if status:
        q = q.filter_by(status=status)

    if not has_role("ADMIN"):
        owner_courts = _get_verified_courts_for_user(g.user)
        if not owner_courts:
            return jsonify(error="Forbidden"), 403
        owner_court_ids = [c.id for c in owner_courts]
        q = (
            q.join(Slot, Booking.slot_id == Slot.id)
             .join(Court, Slot.court_id == Court.id)
             .filter(Court.id.in_(owner_court_ids))
        )

    rows = q.order_by(Booking.created_at.desc()).limit(200).all()
    user_ids = [b.user_id for b in rows]
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return jsonify([
        {
            "id": b.id,
            "user_id": b.user_id,
            "user_full_name": users.get(b.user_id).full_name if users.get(b.user_id) else None,
            "user_phone_number": users.get(b.user_id).phone_number if users.get(b.user_id) else None,
            "slot_id": b.slot_id,
            "status": b.status,
            "created_at": b.created_at.isoformat(),
        } for b in rows
    ]), 200

# ---------- ADMIN: cancel any booking ----------
@booking_bp.post("/bookings/<int:booking_id>/admin_cancel")
@require_roles("ADMIN")
def admin_cancel_booking(booking_id: int):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip() or "Admin cancellation"

    booking = Booking.query.get(booking_id)
    if not booking:
        return jsonify(error="Booking not found"), 404

    if booking.status != "CONFIRMED":
        return jsonify(error="Booking not cancellable"), 400

    payment = Payment.query.filter_by(booking_id=booking.id).first()

    booking.status = "CANCELLED"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = reason
    if payment:
        payment.status = "FAILED"
        db.session.delete(payment)
    db.session.delete(booking)
    db.session.commit()

    log_event("ADMIN_BOOKING_CANCEL", user_id=g.user.id, entity="booking", entity_id=booking_id, metadata={"reason": reason})
    return jsonify(message="Cancelled by admin"), 200
