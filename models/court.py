from datetime import datetime
from models.db import db

class Court(db.Model):
    __tablename__ = "courts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    maps_link = db.Column(db.String(255), nullable=True)
    name_normalized = db.Column(db.String(120), nullable=False)
    location_normalized = db.Column(db.String(160), nullable=False)

    status = db.Column(db.String(20), nullable=False, default="PENDING")
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    rejected_reason = db.Column(db.String(255), nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("maps_link", name="uq_courts_maps_link"),
    )
