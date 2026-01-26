from datetime import datetime
from models.db import db


class LoginOTP(db.Model):
    __tablename__ = "login_otps"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(32), nullable=False, default="LOGIN")

    token_hash = db.Column(db.String(128), unique=True, nullable=False, index=True)
    code_hash = db.Column(db.String(128), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)

    attempts = db.Column(db.Integer, default=0, nullable=False)

    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
