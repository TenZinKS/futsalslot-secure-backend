from datetime import datetime
from models.db import db

class IpRateLimit(db.Model):
    __tablename__ = "ip_rate_limits"

    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), unique=True, nullable=False, index=True)

    window_start = db.Column(db.DateTime, nullable=False)
    count = db.Column(db.Integer, default=0, nullable=False)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
