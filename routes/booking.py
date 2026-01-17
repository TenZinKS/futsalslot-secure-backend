from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from flask import Blueprint, request, jsonify, current_app, g
from models import db
from models.court import Court
from models.slot import Slot
from models.booking import Booking
from security.rbac import require_roles
from utils.auth_context import login_required
from utils.audit import log_event

booking_bp = Blueprint("booking", __name__)

def _parse_iso(dt_str: str):
    # Expect ISO format like "2026-01-20T18:00:00"
    return datetime.fromisoformat(dt_str)

# ---------- STAFF/ADMIN: manage courts ----------
@booking_bp.post("/courts")
@require_roles("ADMIN", "STAFF")
def create_court():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip() or None
    if not name:
        return jsonify(error="Court name required"), 400

    c = Court(name=name, location=location)
    db.session.add(c)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Court name already exists"), 409

    log_event("COURT_CREATE", user_id=g.user.id, entity="court", entity_id=c.id)
    return jsonify(id=c.id, name=c.name, location=c.location), 201


@booking_bp.get("/courts")
@login_required
def list_courts():
    courts = Court.query.filter_by(is_active=True).all()
    return jsonify([
        {"id": c.id, "name": c.name, "location": c.location}
        for c in courts
    ]), 200


# ---------- STAFF/ADMIN: create slots ----------
@booking_bp.post("/slots")
@require_roles("ADMIN", "STAFF")
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

    q = Slot.query.filter_by(is_active=True)
    if court_id:
        q = q.filter_by(court_id=court_id)

    if date_str:
        try:
            day = datetime.fromisoformat(date_str)
        except Exception:
            return jsonify(error="Invalid date. Use YYYY-MM-DD"), 400
        start = datetime(day.year, day.month, day.day)
        end = start + timedelta(days=1)
        q = q.filter(Slot.start_time >= start, Slot.start_time < end)

    slots = q.order_by(Slot.start_time.asc()).all()

    # mark availability by checking if booking exists
    slot_ids = [s.id for s in slots]
    booked = set(
        r.slot_id for r in Booking.query.filter(Booking.slot_id.in_(slot_ids), Booking.status == "CONFIRMED").all()
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
    data = request.get_json(silent=True) or {}
    slot_id = data.get("slot_id")
    if not slot_id:
        return jsonify(error="slot_id required"), 400

    slot = Slot.query.get(slot_id)
    if not slot or not slot.is_active:
        return jsonify(error="Slot not found"), 404

    # Optional: prevent booking past slots
    if slot.start_time <= datetime.utcnow():
        return jsonify(error="Cannot book past/started slots"), 400

    booking = Booking(user_id=g.user.id, slot_id=slot_id, status="CONFIRMED")
    db.session.add(booking)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Unique constraint uq_booking_slot_once triggers here
        log_event("BOOKING_FAIL_ALREADY_BOOKED", user_id=g.user.id, entity="slot", entity_id=slot_id)
        return jsonify(error="Slot already booked"), 409

    log_event("BOOKING_CREATE", user_id=g.user.id, entity="booking", entity_id=booking.id, metadata={"slot_id": slot_id})
    return jsonify(id=booking.id, status=booking.status), 201


# ---------- PLAYERS: cancel booking (policy window) ----------
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

    slot = Slot.query.get(booking.slot_id)
    cutoff_hours = current_app.config.get("CANCEL_CUTOFF_HOURS", 12)
    if slot and (slot.start_time - datetime.utcnow()).total_seconds() < cutoff_hours * 3600:
        return jsonify(error=f"Cancellation not allowed within {cutoff_hours} hours of start"), 403

    booking.status = "CANCELLED"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = reason
    db.session.commit()

    log_event("BOOKING_CANCEL", user_id=g.user.id, entity="booking", entity_id=booking.id, metadata={"reason": reason})
    return jsonify(message="Cancelled"), 200

# ---------- PLAYERS: view my bookings ----------
@booking_bp.get("/bookings/me")
@login_required
def my_bookings():
    # optional: status filter
    status = request.args.get("status")  # CONFIRMED/CANCELLED
    q = Booking.query.filter_by(user_id=g.user.id)
    if status:
        q = q.filter_by(status=status)

    rows = q.order_by(Booking.created_at.desc()).all()

    # Fetch slot info for each booking
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


# ---------- STAFF/ADMIN: deactivate slot ----------
@booking_bp.post("/slots/<int:slot_id>/deactivate")
@require_roles("ADMIN", "STAFF")
def deactivate_slot(slot_id: int):
    slot = Slot.query.get(slot_id)
    if not slot:
        return jsonify(error="Slot not found"), 404

    slot.is_active = False
    db.session.commit()

    log_event("SLOT_DEACTIVATE", user_id=g.user.id, entity="slot", entity_id=slot_id)
    return jsonify(message="Slot deactivated"), 200

# ---------- STAFF/ADMIN: list all bookings ----------
@booking_bp.get("/bookings")
@require_roles("ADMIN", "STAFF")
def list_all_bookings():
    status = request.args.get("status")
    q = Booking.query
    if status:
        q = q.filter_by(status=status)

    rows = q.order_by(Booking.created_at.desc()).limit(200).all()
    return jsonify([
        {
            "id": b.id,
            "user_id": b.user_id,
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

    booking.status = "CANCELLED"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = reason
    db.session.commit()

    log_event("ADMIN_BOOKING_CANCEL", user_id=g.user.id, entity="booking", entity_id=booking.id, metadata={"reason": reason})
    return jsonify(message="Cancelled by admin"), 200
