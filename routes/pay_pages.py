import os

from flask import Blueprint, request

from models import db
from models.payment import Payment
from utils.audit import log_event

pay_pages_bp = Blueprint("pay_pages", __name__)

@pay_pages_bp.get("/pay/success")
def pay_success():
    # Simple page Stripe redirects to after payment
    base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
    bookings_url = f"{base_url}/bookings"
    return """
    <html>
      <head><title>Payment Success</title></head>
      <body style="font-family: system-ui; max-width: 720px; margin: 40px auto;">
        <h1>Payment Successful ✅</h1>
        <p>Your payment was accepted. Your booking will be confirmed automatically (via Stripe webhook).</p>
        <p>You can now return to the app and check <b>My Bookings</b>.</p>
        <a href=\"""" + bookings_url + """\" style="display: inline-block; padding: 12px 18px; background: #0ea5e9; color: white; text-decoration: none; border-radius: 8px; font-weight: 600;">Go to My Bookings</a>
      </body>
    </html>
    """, 200

@pay_pages_bp.get("/pay/cancel")
def pay_cancel():
    payment_id = request.args.get("payment_id", type=int)

    payment = Payment.query.get(payment_id) if payment_id else None
    if payment and payment.status != "PAID":
        payment.status = "FAILED"
        db.session.delete(payment)
        db.session.commit()
        log_event("PAYMENT_CANCELLED", user_id=None, entity="payment", entity_id=payment.id, metadata={"reason": "stripe_cancel"})

    return """
    <html>
      <head><title>Payment Cancelled</title></head>
      <body style="font-family: system-ui; max-width: 720px; margin: 40px auto;">
        <h1>Payment Cancelled ❌</h1>
        <p>No payment was taken. You can try booking again from the Slots page.</p>
      </body>
    </html>
    """, 200
