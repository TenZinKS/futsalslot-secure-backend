from datetime import datetime
from models.db import db

class Court(db.Model):
    __tablename__ = "courts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)  # e.g. "Court A"
    location = db.Column(db.String(120), nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
