from datetime import datetime
from models.db import db


class BlockedEmail(db.Model):
    __tablename__ = "blocked_emails"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    email_normalized = db.Column(db.String(255), nullable=False, unique=True, index=True)
    reason = db.Column(db.String(255), nullable=True)
    blocked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
