import os
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

import stripe
from flask import Blueprint, request, jsonify, g

from models import db
from models.booking import Booking
from models.slot import Slot
from models.payment import Payment
from utils.auth_context import login_required
from utils.audit import log_event

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

def _append_query(url: str, params: dict) -> str:
    if not url:
        return url
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query))
    query.update({k: v for k, v in params.items() if v is not None})
    new_query = urlencode(query)
    return urlunparse(parts._replace(query=new_query))


@payments_bp.post("/start")
@login_required
def start_payment():
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        return jsonify(error="Stripe secret key missing (STRIPE_SECRET_KEY)"), 500
    data = request.get_json(silent=True) or {}
    booking_id = data.get("booking_id")
    slot_id = data.get("slot_id")

    booking = None
    if booking_id:
        booking = Booking.query.get(int(booking_id))
        if not booking or booking.user_id != g.user.id:
            return jsonify(error="Booking not found"), 404
        if booking.status == "CONFIRMED":
            return jsonify(error="Booking already confirmed"), 400
        slot_id = booking.slot_id

    if not slot_id:
        return jsonify(error="slot_id required"), 400

    slot = Slot.query.get(int(slot_id))
    if not slot or not slot.is_active:
        return jsonify(error="Slot not found"), 404

    existing_confirmed = Booking.query.filter_by(slot_id=slot.id, status="CONFIRMED").first()
    if existing_confirmed:
        return jsonify(error="Slot already booked"), 409

    if booking:
        payment = Payment.query.filter_by(booking_id=booking.id).first()
        if payment:
            db.session.delete(payment)
        db.session.delete(booking)
        db.session.commit()

    payment = Payment(
        booking_id=None,
        slot_id=slot.id,
        provider="STRIPE",
        amount=int(slot.price),
        currency="NPR",
        status="INIT",
    )
    db.session.add(payment)
    db.session.commit()

    success_url = os.getenv("STRIPE_SUCCESS_URL")
    cancel_url = os.getenv("STRIPE_CANCEL_URL")

    if not stripe.api_key:
        return jsonify(error="Stripe secret key not configured"), 500
    if not success_url or not cancel_url:
        return jsonify(error="Stripe success/cancel URLs not configured"), 500

    # store price in rupees in DB (1500)
    amount_rupees = int(slot.price)
    amount_paisa = amount_rupees * 100  # Stripe expects smallest unit for NPR

    # (optional) keep your Payment.amount as rupees (fine)
    payment.amount = amount_rupees
    payment.currency = "NPR"
    db.session.commit()

    cancel_url = _append_query(cancel_url, {"booking_id": "", "payment_id": str(payment.id)})

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "npr",
                "product_data": {"name": f"Court booking (Slot #{slot.id})"},
                "unit_amount": amount_paisa, 
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "booking_id": "",
            "payment_id": str(payment.id),
            "user_id": str(g.user.id),
            "slot_id": str(slot.id),
        },
    )


    payment.stripe_session_id = session["id"]
    db.session.commit()

    log_event("PAYMENT_SESSION_CREATED", user_id=g.user.id, entity="payment", entity_id=payment.id, metadata={"stripe_session_id": session["id"]})
    return jsonify(checkout_url=session["url"]), 200


@payments_bp.get("/cancel")
@login_required
def cancel_payment():
    payment_id = request.args.get("payment_id", type=int)
    payment = Payment.query.get(payment_id) if payment_id else None
    if not payment:
        return jsonify(error="Payment not found"), 404
    if payment.status == "PAID":
        return jsonify(error="Payment already confirmed"), 400

    db.session.delete(payment)
    db.session.commit()
    log_event("PAYMENT_CANCELLED", user_id=g.user.id, entity="payment", entity_id=payment.id, metadata={"reason": "user_cancelled"})
    return jsonify(message="Payment cancelled"), 200
