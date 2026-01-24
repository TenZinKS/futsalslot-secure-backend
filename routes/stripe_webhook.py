import os
import stripe
from datetime import datetime
from flask import Blueprint, request, jsonify

from models import db
from models.booking import Booking
from models.payment import Payment
from utils.audit import log_event

webhook_bp = Blueprint("webhook", __name__, url_prefix="/webhooks")


@webhook_bp.post("/stripe")
def stripe_webhook():
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    sig_header = request.headers.get("Stripe-Signature")
    payload = request.data

    if not endpoint_secret:
        return jsonify(error="Webhook secret not configured"), 500

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        return jsonify(error="Invalid webhook signature"), 400

    event_type = event.get("type")
    if event_type in ("checkout.session.completed", "checkout.session.expired"):
        session = event["data"]["object"]
        session_id = session.get("id")
        meta = session.get("metadata", {}) or {}

        payment_id = meta.get("payment_id")
        booking_id = meta.get("booking_id")

        payment = None
        if payment_id:
            payment = Payment.query.get(int(payment_id))
        if not payment and session_id:
            payment = Payment.query.filter_by(stripe_session_id=session_id).first()

        booking = Booking.query.get(payment.booking_id) if payment and payment.booking_id else None

        if event_type == "checkout.session.completed":
            if payment and payment.status != "PAID":
                slot_id = meta.get("slot_id")
                user_id = meta.get("user_id")
                if slot_id and user_id:
                    existing = Booking.query.filter_by(slot_id=int(slot_id), status="CONFIRMED").first()
                    if existing:
                        payment.status = "FAILED"
                    else:
                        booking = Booking(user_id=int(user_id), slot_id=int(slot_id), status="CONFIRMED")
                        db.session.add(booking)
                        db.session.flush()
                        payment.booking_id = booking.id
                        payment.status = "PAID"
                        payment.paid_at = datetime.utcnow()

                db.session.commit()
                log_event("PAYMENT_PAID", user_id=None, entity="payment", entity_id=payment.id, metadata={"stripe_session_id": session_id, "booking_id": payment.booking_id})
        else:
            if payment and payment.status != "PAID":
                payment.status = "FAILED"
                db.session.delete(payment)
                db.session.commit()
                log_event("PAYMENT_EXPIRED", user_id=None, entity="payment", entity_id=payment.id, metadata={"stripe_session_id": session_id, "booking_id": payment.booking_id})

    return jsonify(received=True), 200
