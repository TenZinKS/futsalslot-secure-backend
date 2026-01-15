from datetime import datetime
from models.db import db

class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # store only hashed token in DB (never store raw token)
    token_hash = db.Column(db.String(128), unique=True, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)  # ✅ add this
    expires_at = db.Column(db.DateTime, nullable=False)

    revoked = db.Column(db.Boolean, default=False, nullable=False)

    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
