from datetime import datetime
from models.db import db

# association table for many-to-many User <-> Role
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    phone_number = db.Column(db.String(30), nullable=True)

    # future fields for MFA + lockouts (we’ll implement later)
    mfa_enabled = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    password_changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    roles = db.relationship("Role", secondary=user_roles, back_populates="users")

class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # e.g. PLAYER, STAFF, ADMIN

    users = db.relationship("User", secondary=user_roles, back_populates="roles")
