from datetime import datetime
from models.db import db

class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=True, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slots.id"), nullable=True, index=True)

    provider = db.Column(db.String(20), nullable=False, default="STRIPE")
    amount = db.Column(db.Integer, nullable=False)   # smallest unit
    currency = db.Column(db.String(10), nullable=False, default="NPR")

    status = db.Column(db.String(20), nullable=False, default="INIT")  # INIT, PAID, FAILED
    stripe_session_id = db.Column(db.String(255), nullable=True, unique=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=True)
