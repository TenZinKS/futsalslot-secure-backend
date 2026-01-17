from datetime import datetime
from models.db import db

class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"

    id = db.Column(db.Integer, primary_key=True)

    # We track both email + ip to stop both targeted and broad attacks
    email = db.Column(db.String(255), nullable=False, index=True)
    ip = db.Column(db.String(64), nullable=False, index=True)

    fail_count = db.Column(db.Integer, default=0, nullable=False)
    last_fail_at = db.Column(db.DateTime, nullable=True)
    locked_until = db.Column(db.DateTime, nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
