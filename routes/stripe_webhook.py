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

    if event["type"] == "checkout.session.completed":
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

        if payment and payment.status != "PAID":
            payment.status = "PAID"
            payment.paid_at = datetime.utcnow()

            booking = Booking.query.get(payment.booking_id)
            if booking and booking.status != "CONFIRMED":
                booking.status = "CONFIRMED"

            db.session.commit()
            log_event("PAYMENT_PAID", user_id=None, entity="payment", entity_id=payment.id, metadata={"stripe_session_id": session_id, "booking_id": payment.booking_id})

    return jsonify(received=True), 200
