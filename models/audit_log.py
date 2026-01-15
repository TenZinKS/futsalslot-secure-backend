from datetime import datetime
from models.db import db

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)  # nullable for unauth events
    action = db.Column(db.String(80), nullable=False)  # e.g. LOGIN_FAIL, BOOKING_CREATE
    entity = db.Column(db.String(80), nullable=True)   # e.g. booking, user
    entity_id = db.Column(db.String(80), nullable=True)

    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
