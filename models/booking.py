from datetime import datetime
from models.db import db

class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slots.id"), nullable=False, index=True)

    status = db.Column(db.String(20), nullable=False, default="CONFIRMED")
    # status values: CONFIRMED, CANCELLED

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancel_reason = db.Column(db.String(120), nullable=True)

    __table_args__ = (
        # Hard business-rule: only one booking can exist per slot (prevents double booking)
        db.UniqueConstraint("slot_id", name="uq_booking_slot_once"),
    )
