import os
import stripe
from flask import Blueprint, request, jsonify, g

from models import db
from models.booking import Booking
from models.slot import Slot
from models.payment import Payment
from utils.auth_context import login_required
from utils.audit import log_event

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

@payments_bp.post("/start")
@login_required
def start_payment():
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        return jsonify(error="Stripe secret key missing (STRIPE_SECRET_KEY)"), 500
    data = request.get_json(silent=True) or {}
    booking_id = data.get("booking_id")
    if not booking_id:
        return jsonify(error="booking_id required"), 400

    booking = Booking.query.get(int(booking_id))
    if not booking or booking.user_id != g.user.id:
        return jsonify(error="Booking not found"), 404

    if booking.status == "CONFIRMED":
        return jsonify(error="Booking already confirmed"), 400

    slot = Slot.query.get(booking.slot_id)
    if not slot or not slot.is_active:
        return jsonify(error="Slot not found"), 404

    # create payment record (1 payment per booking)
    payment = Payment.query.filter_by(booking_id=booking.id).first()
    if not payment:
        payment = Payment(
            booking_id=booking.id,
            provider="STRIPE",
            amount=int(slot.price),
            currency="NPR",
            status="INIT",
        )
        db.session.add(payment)
        db.session.commit()

    # ensure booking is pending payment
    booking.status = "PENDING_PAYMENT"
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

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "npr",
                "product_data": {"name": f"Futsal booking (Slot #{slot.id})"},
                "unit_amount": amount_paisa, 
            },
            "quantity": 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "booking_id": str(booking.id),
            "payment_id": str(payment.id),
            "user_id": str(g.user.id),
        },
    )


    payment.stripe_session_id = session["id"]
    db.session.commit()

    log_event("PAYMENT_SESSION_CREATED", user_id=g.user.id, entity="payment", entity_id=payment.id, metadata={"stripe_session_id": session["id"]})
    return jsonify(checkout_url=session["url"]), 200
