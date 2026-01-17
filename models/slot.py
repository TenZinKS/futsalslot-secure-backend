from datetime import datetime
from models.db import db

class Slot(db.Model):
    __tablename__ = "slots"

    id = db.Column(db.Integer, primary_key=True)

    court_id = db.Column(db.Integer, db.ForeignKey("courts.id"), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)

    price = db.Column(db.Integer, nullable=False, default=0)  # store smallest unit (e.g., NPR)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Prevent duplicate slot times for same court
        db.UniqueConstraint("court_id", "start_time", "end_time", name="uq_court_timeslot"),
    )
